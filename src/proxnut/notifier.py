"""Notification system for proxnut"""

import json
import os
import requests
from datetime import datetime, timezone
from typing import List, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s.%(funcName)s): %(message)s",
)
logger = logging.getLogger(__name__)

COLOR_MAP = {
    "red": 0xFF0000,
    "orange-red": 0xFF4500,
    "green": 0x00FF00,
}


class Notifier:
    """Notification handler for Discord and other services"""

    def __init__(self):
        """Initialize notifier with configuration"""
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

        if self.is_discord_enabled():
            logger.info("Discord notifications are enabled.")

    def is_discord_enabled(self) -> bool:
        """Check if Discord notifications are enabled"""
        return bool(self.discord_webhook_url)

    def __logging(
        self,
        title: str,
        description: str,
        color: int = 0xFF0000,
    ) -> bool:
        """Log notification details"""
        message = json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "description": description,
            }
        )
        if color == COLOR_MAP["red"]:
            logger.error(message)
        elif color == COLOR_MAP["orange-red"]:
            logger.warning(message)
        else:
            logger.info(message)
        return True

    def __send_discord_notification(
        self,
        title: str,
        description: str,
        color: int = 0xFF0000,
        thumbnail_url: Optional[str] = None,
    ) -> bool:
        """Send notification to Discord via webhook"""
        if not self.is_discord_enabled():
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "proxnut UPS Monitor"},
        }

        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        payload = {"embeds": [embed]}

        response = requests.post(
            self.discord_webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        return response.status_code == 204

    def send(self, title: str, description: str, color: int):
        self.__logging(title, description, color)
        if self.discord_webhook_url:
            return self.__send_discord_notification(title, description, color)

    def notify_power_loss(
        self, ups_status: str, target_hosts: List[str], shutdown_delay: int = 0
    ):
        """Send notification about UPS power loss"""
        target_hosts_str = ", ".join(target_hosts)

        title = "🔴 UPS Power Loss Detected!"
        description = (
            f"⚠️ **UPS Status:** {ups_status}\n"
            f"🖥️ **Target Hosts:** {target_hosts_str}\n"
            f"⏱️ **Shutdown Delay:** {shutdown_delay} seconds"
        )
        color = COLOR_MAP["orange-red"]

        self.send(title, description, color)

    def notify_power_recovered(self):
        """Send notification about UPS power recovery"""
        title = "🟢 UPS Power Recovered!"
        description = "🛑 **Shutdown Cancelled**"
        color = COLOR_MAP["green"]

        self.send(title, description, color)

    def notify_shutdown_executed(
        self,
        target_hosts: List[str],
        successful_nodes: List[str],
        failed_nodes: List[str],
    ):
        """Send notification about shutdown execution"""
        target_hosts_str = ", ".join(target_hosts)

        title = f"🔴 Shutdown Executed: {len(target_hosts) - len(failed_nodes)}/{len(target_hosts)}"
        success_str = ", ".join(successful_nodes) if successful_nodes else "None"
        failed_str = ", ".join(failed_nodes)
        description = (
            f"🖥️ **Target Hosts:** {target_hosts_str}\n"
            f"✅ **Successful:** {success_str}\n"
            f"❌ **Failed:** {failed_str}"
        )
        color = COLOR_MAP["red"]

        self.send(title, description, color)

    def notify_error(self, error_message: str, context: str = ""):
        """Send notification about errors"""

        title = "🔴 proxnut Error"
        description = f"❌ **Error:** {error_message}"
        if context:
            description += f"\n📍 **Context:** {context}"
        color = COLOR_MAP["red"]

        self.send(title, description, color)
