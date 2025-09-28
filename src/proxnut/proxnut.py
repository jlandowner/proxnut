import threading
import signal
import logging
import os
import json
import requests
from datetime import datetime
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
SHUTDOWN_DELAY = int(os.getenv("PROXNUT_SHUTDOWN_DELAY", "0"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Global timer reference for cancellation
timer = None
shutdown_timer = None
shutdown_requested = False
shutdown_in_progress = False


def shutdown_proxmox_nodes(prox: ProxmoxAPI):
    nodes = prox.nodes.get()
    if nodes is None:
        raise Exception("Failed to retrieve nodes from Proxmox API.")

    for node in nodes:
        try:
            if node["node"] in TARGET_MACHINES:
                logger.info("Shutting down node: %s", node["node"])
                prox.nodes(node["node"]).status.post(command="shutdown")
        except Exception as e:
            logger.error("Error shutting down node %s: %s", node["node"], e)
            continue
    else:
        logger.info("All nodes have been processed.")


UPS_STATUS = "ups.status"


def signal_handler(signum, _frame):
    """Handle graceful shutdown on SIGINT and SIGTERM"""
    global timer, shutdown_timer, shutdown_requested
    logger.info("Received signal %s. Gracefully shutting down...", signum)
    shutdown_requested = True
    if timer is not None:
        timer.cancel()
        logger.info("Cancelled running timer.")
    if shutdown_timer is not None:
        shutdown_timer.cancel()
        logger.info("Cancelled shutdown timer.")


# Properly decode bytes to strings
def decode_if_bytes(obj):
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    return str(obj)


def send_discord_notification(title, description, color=0xFF0000, thumbnail_url=None):
    """Send notification to Discord via webhook"""
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook URL not configured, skipping notification")
        return

    try:
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "proxnut UPS Monitor"
            }
        }

        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        payload = {
            "embeds": [embed]
        }

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 204:
            logger.info("Discord notification sent successfully")
        else:
            logger.warning("Discord notification failed with status %d: %s",
                         response.status_code, response.text)

    except Exception as e:
        logger.error("Failed to send Discord notification: %s", e)


def execute_shutdown(prox, ups_name, nut_client):
    """Execute the actual shutdown after delay"""
    global shutdown_in_progress

    # Final check before shutdown - verify UPS is still in bad state
    try:
        ups_vars = nut_client.GetUPSVars(ups_name)
        ups_vars = {decode_if_bytes(k): decode_if_bytes(v) for k, v in ups_vars.items()}
        status = ups_vars.get(UPS_STATUS, "")

        if status in UPS_NORMAL_STATUSES:
            logger.info("UPS recovered to normal status (%s) before shutdown. Cancelling shutdown.", status)
            shutdown_in_progress = False
            return

        logger.warning("UPS still in abnormal state (%s). Proceeding with shutdown.", status)
        shutdown_proxmox_nodes(prox)

    except Exception as e:
        logger.error("Error checking UPS status before shutdown: %s", e)
        logger.warning("Proceeding with shutdown due to previous power issue.")
        shutdown_proxmox_nodes(prox)

    shutdown_in_progress = False


def schedule_delayed_shutdown(prox, ups_name, nut_client, ups_status):
    """Schedule shutdown with delay and recovery checking"""
    global shutdown_timer, shutdown_in_progress

    # Send Discord notification about power loss
    target_hosts = ", ".join(TARGET_MACHINES)
    if SHUTDOWN_DELAY > 0:
        shutdown_in_progress = True
        description = f"⚠️ **UPS Status:** {ups_status}\n🖥️ **Target Hosts:** {target_hosts}\n⏱️ **Shutdown Delay:** {SHUTDOWN_DELAY} seconds\n📊 **Monitoring for recovery...**"
        send_discord_notification(
            "🔴 UPS Power Loss Detected!",
            description,
            color=0xFF4500  # Orange-red
        )
        logger.warning("Scheduling shutdown in %d seconds. Monitoring for UPS recovery...", SHUTDOWN_DELAY)
        shutdown_timer = threading.Timer(SHUTDOWN_DELAY, execute_shutdown, args=[prox, ups_name, nut_client])
        shutdown_timer.start()
    else:
        description = f"⚠️ **UPS Status:** {ups_status}\n🖥️ **Target Hosts:** {target_hosts}\n⚡ **Action:** Immediate shutdown"
        send_discord_notification(
            "🔴 UPS Power Loss - Immediate Shutdown!",
            description,
            color=0xFF0000  # Red
        )
        logger.warning("No shutdown delay configured. Executing immediate shutdown.")
        shutdown_proxmox_nodes(prox)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("Signal handlers registered for SIGINT and SIGTERM.")

    if SHUTDOWN_DELAY > 0:
        logger.info("Shutdown delay configured: %d seconds", SHUTDOWN_DELAY)
    else:
        logger.info("No shutdown delay configured - immediate shutdown on power loss")

    nut_client = PyNUT.PyNUTClient(
        host=os.getenv("NUT_HOST", "localhost"),
        port=int(os.getenv("NUT_PORT", "3493")),
    )
    ups_names = nut_client.GetUPSNames()
    logger.info("Available UPS names: %s", ups_names)

    ups_name = os.getenv("NUT_UPS_NAME", "")
    if ups_name not in ups_names:
        raise Exception("UPS not found: {} in {}".format(ups_name, ups_names))

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
    res = prox.nodes.get() or []
    nodes = [node["node"] for node in res] if (nodes := prox.nodes.get()) else []
    logger.info("Proxmox nodes: %s", nodes)

    if not set(TARGET_MACHINES).issubset(set(nodes)):
        raise Exception(
            "Some target machines not found in Proxmox nodes. Targets: {}, Nodes: {}".format(
                TARGET_MACHINES, nodes
            )
        )

    def check_ups_status():
        global timer, shutdown_timer, shutdown_in_progress

        prox.nodes.get()  # Simple call to check connection

        ups_vars = nut_client.GetUPSVars(ups_name)

        ups_vars = {decode_if_bytes(k): decode_if_bytes(v) for k, v in ups_vars.items()}

        status = ups_vars.get(UPS_STATUS, "")

        if status not in UPS_NORMAL_STATUSES:
            # UPS has power issue
            if not shutdown_in_progress:
                logger.warning(
                    "UPS status indicates power issue (%s). Initiating shutdown process.", status
                )
                schedule_delayed_shutdown(prox, ups_name, nut_client, status)
                return
            else:
                logger.info("UPS status still abnormal (%s). Shutdown already in progress.", status)
        else:
            # UPS status is normal
            if shutdown_in_progress:
                # Cancel pending shutdown - UPS recovered!
                logger.info("UPS recovered to normal status (%s). Cancelling pending shutdown.", status)

                # Send Discord notification about recovery
                target_hosts = ", ".join(TARGET_MACHINES)
                description = f"✅ **UPS Status:** {status}\n🖥️ **Target Hosts:** {target_hosts}\n🛑 **Shutdown Cancelled**"
                send_discord_notification(
                    "🟢 UPS Power Recovered!",
                    description,
                    color=0x00FF00  # Green
                )

                if shutdown_timer is not None:
                    shutdown_timer.cancel()
                    shutdown_timer = None
                shutdown_in_progress = False
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
