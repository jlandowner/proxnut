import threading
import signal
import logging
import os
from dotenv import load_dotenv
from PyNUTClient import PyNUT
from proxmoxer import ProxmoxAPI

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(funcName)s): %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_MACHINES = os.getenv("PROXNUT_SHUTDOWN_HOSTS", "").split(",")
UPS_NORMAL_STATUSES = os.getenv("UPS_NORMAL_STATUSES", "OL,OL CHRG").split(",")

# Global timer reference for cancellation
timer = None
shutdown_requested = False


def shutdown_proxmox_nodes():
    prox = ProxmoxAPI(
        host=os.getenv("PROXMOX_HOST", "localhost"),
        port=int(os.getenv("PROXMOX_PORT", "8006")),
        verify_ssl=os.getenv("PROXMOX_VERIFY_TLS", "").lower()
        in [
            "true",
            "1",
        ],
        user=os.getenv("PROXMOX_USER", "example@pam"),
        token_name=os.getenv("PROXMOX_TOKEN_NAME", "proxnut"),
        token_value=os.getenv("PROXMOX_TOKEN", "******"),
        timeout=int(os.getenv("PROXMOX_TIMEOUT", "30")),
    )

    nodes = prox.nodes.get()
    if nodes is None:
        raise Exception("Failed to retrieve nodes from Proxmox API.")

    for node in nodes:
        if node["node"] in TARGET_MACHINES:
            logger.info("Shutting down node: %s", node["node"])
            prox.nodes(node["node"]).status.post(command="shutdown")
    else:
        logger.info("All nodes have been processed.")


UPS_STATUS = "ups.status"


def signal_handler(signum, frame):
    """Handle graceful shutdown on SIGINT and SIGTERM"""
    global timer, shutdown_requested
    logger.info("Received signal %s. Gracefully shutting down...", signum)
    shutdown_requested = True
    if timer is not None:
        timer.cancel()
        logger.info("Cancelled running timer.")


# Properly decode bytes to strings
def decode_if_bytes(obj):
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    return str(obj)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("Signal handlers registered for SIGINT and SIGTERM.")

    nut_client = PyNUT.PyNUTClient(
        host=os.getenv("NUT_HOST", "localhost"),
        port=int(os.getenv("NUT_PORT", "3493")),
    )
    ups_names = nut_client.GetUPSNames()

    ups_name = os.getenv("NUT_UPS_NAME", "")
    if ups_name not in ups_names:
        raise Exception("UPS not found: {} in {}".format(ups_name, ups_names))

    def check_ups_status():
        global timer

        ups_vars = nut_client.GetUPSVars(ups_name)

        ups_vars = {decode_if_bytes(k): decode_if_bytes(v) for k, v in ups_vars.items()}

        status = ups_vars.get(UPS_STATUS, "")
        if status not in UPS_NORMAL_STATUSES:
            logger.warning(
                "UPS status indicates power issue (%s). Initiating shutdown.", status
            )
            shutdown_proxmox_nodes()
            return
        else:
            logger.info("UPS status is normal (%s). No action required.", status)

        # Schedule next check
        if shutdown_requested:
            logger.info("Shutdown requested. Not scheduling further checks.")
            return

        timer = threading.Timer(
            int(os.getenv("PROXNUT_CHECK_INTERVAL", "5")), check_ups_status
        )
        timer.start()

    check_ups_status()


if __name__ == "__main__":
    main()
