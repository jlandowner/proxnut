"""Main proxnut application logic"""

import sys
import threading
import signal
import logging
import os
import traceback
from typing import Optional
from dotenv import load_dotenv

from .proxmox_client import ProxmoxClient
from .ups_client import UPSClient, UPSStatusNotNormalError
from .notifier import Notifier

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(funcName)s): %(message)s",
)
logger = logging.getLogger(__name__)


class ValidateError(Exception):
    """Custom exception for validation errors"""

    pass


class ProxnutMonitor:
    """Main monitoring class that orchestrates UPS monitoring and Proxmox shutdown"""

    def __init__(self):
        """Initialize the monitor with all required clients"""
        self.init_clients()

        # Load configuration from environment
        self.target_machines = [
            machine.strip()
            for machine in os.getenv("PROXNUT_SHUTDOWN_HOSTS", "").split(",")
            if machine.strip()
        ]
        self.shutdown_delay = int(os.getenv("PROXNUT_SHUTDOWN_DELAY", "0"))
        self.default_check_interval = int(os.getenv("PROXNUT_CHECK_INTERVAL", "5"))
        self.check_interval = self.default_check_interval
        self.max_check_error_limits = int(os.getenv("MAX_CHECK_ERROR_LIMITS", "5"))

        # Instance state
        self.monitoring_timer = None
        self.shutdown_timer = None
        self.error_count = 0

    def init_clients(self):
        self.proxmox_client = ProxmoxClient()
        self.ups_client = UPSClient()
        self.notifier = Notifier()

    def validate(self):
        """Validate all configuration and connections"""
        # Validate UPS configuration
        logger.info("Validating UPS configuration...")
        if not self.ups_client.ups_name:
            raise ValidateError("UPS name not configured (NUT_UPS_NAME)")

        if not self.ups_client.validate_ups_name():
            available_names = self.ups_client.get_ups_names()
            raise ValidateError("UPS name not found", available_names)

        # Validate Proxmox configuration
        logger.info("Validating Proxmox configuration...")
        if not self.target_machines:
            raise ValidateError("No target machines configured")

        if not self.proxmox_client.validate_target_nodes(self.target_machines):
            available_nodes = self.proxmox_client.get_nodes()
            raise ValidateError(
                "Target nodes not found in Proxmox cluster", available_nodes
            )

    def __execute_shutdown(self) -> None:
        """Execute the actual shutdown after delay"""

        # Recover UPS status before shutdown
        try:
            self.ups_client.check_ups_status_normal()

            logger.info("UPS power restored. Cancelling scheduled shutdown.")
            self.notifier.notify_power_recovered()
            self.stop_shutdown_timer()
            return

        except UPSStatusNotNormalError:
            logger.info("UPS still on battery. Proceeding with shutdown.")

        # Stop monitoring
        self.stop_monitoring_timer()
        self.stop_shutdown_timer()

        # Execute shutdown
        logger.info("Initiating shutdown of target nodes: %s", self.target_machines)
        results = self.proxmox_client.shutdown_nodes(self.target_machines)

        # Analyze results
        successful_nodes = [node for node, success in results.items() if success]
        failed_nodes = [node for node, success in results.items() if not success]

        self.notifier.notify_shutdown_executed(
            self.target_machines, successful_nodes, failed_nodes
        )

        # Exit
        logger.info("Shutdown process completed. Exiting proxnut.")
        sys.exit(0)

    def start_shutdown_timer(self) -> None:
        """Schedule shutdown with delay and recovery checking"""

        if self.shutdown_timer is not None:
            logger.info("Shutdown already scheduled. Ignoring new shutdown request.")
            return

        if self.shutdown_delay > 0:
            logger.warning(
                "Scheduling shutdown in %d seconds. Monitoring for UPS recovery...",
                self.shutdown_delay,
            )
            self.shutdown_timer = threading.Timer(
                self.shutdown_delay, self.__execute_shutdown
            )
            self.shutdown_timer.start()
        else:
            logger.warning(
                "No shutdown delay configured. Executing immediate shutdown."
            )
            self.__execute_shutdown()

    def stop_shutdown_timer(self) -> None:
        """Cancel any scheduled shutdown"""
        if self.shutdown_timer is not None:
            self.shutdown_timer.cancel()
            self.shutdown_timer = None
            logger.info("Cancelled scheduled shutdown.")

    def is_shutdown_scheduled(self) -> bool:
        """Check if a shutdown is currently scheduled"""
        return self.shutdown_timer is not None

    def start_shutdown_timer_timer(self) -> None:
        """Check UPS status and handle power events"""

        def reschedule_next_check(interval: Optional[int] = None):
            if interval is not None:
                self.check_interval = interval

            self.monitoring_timer = threading.Timer(
                self.check_interval, self.start_shutdown_timer_timer
            )
            self.monitoring_timer.start()

        try:
            # Check Proxmox connection
            self.proxmox_client.api.nodes.get()

            # Check UPS status is normal
            self.ups_client.check_ups_status_normal()

            logger.info(
                "UPS status normal. Next check in %d seconds.", self.check_interval
            )

            # Detect power recovery
            if self.is_shutdown_scheduled():
                logger.info("UPS power restored. Cancelling scheduled shutdown.")
                self.notifier.notify_power_recovered()
                self.stop_shutdown_timer()

            # Reschedule next check
            reschedule_next_check(self.default_check_interval)

        except UPSStatusNotNormalError as e:
            # Detect power loss!
            self.notifier.notify_power_loss(
                e.status, self.target_machines, self.shutdown_delay
            )
            self.start_shutdown_timer()

            # Reschedule next check
            reschedule_next_check(self.default_check_interval)

        except Exception as e:
            self.error_count += 1

            # Retry checking, just logging
            st = traceback.format_exc()
            self.notifier.notify_error(f"Unexpected Error: {e}", st)

            # backoff next check interval
            reschedule_next_check(self.check_interval * 2)

        finally:
            # Check if we've exceeded the maximum error limits
            if self.error_count > self.max_check_error_limits:
                self.stop_monitoring_timer()
                self.stop_shutdown_timer()

                sys.exit(1)

    def stop_monitoring_timer(self) -> None:
        """Cancel any scheduled monitoring"""
        if self.monitoring_timer is not None:
            self.monitoring_timer.cancel()
            self.monitoring_timer = None
            logger.info("Cancelled scheduled monitoring.")

    def signal_handler(self, signum, _frame):
        """Handle graceful shutdown on SIGINT and SIGTERM"""
        logger.info("Received signal %s. Gracefully shutting down...", signum)

        self.stop_monitoring_timer()
        self.stop_shutdown_timer()


def main():
    """Main entry point for proxnut"""
    # Initialize monitor
    monitor = ProxnutMonitor()
    logger.info("ProxnutMonitor initialized")

    # Register signal handlers
    signal.signal(signal.SIGINT, monitor.signal_handler)
    signal.signal(signal.SIGTERM, monitor.signal_handler)
    logger.info("Signal handlers registered for SIGINT and SIGTERM.")

    # Validate configuration
    monitor.validate()
    logger.info("Successfully validated configuration.")

    # Start monitoring
    monitor.start_shutdown_timer_timer()


if __name__ == "__main__":
    main()
