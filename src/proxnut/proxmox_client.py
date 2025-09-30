"""Proxmox client wrapper"""

import os
from typing import List, Dict
from proxmoxer import ProxmoxAPI


class ProxmoxConnectionError(Exception):
    """Custom exception for Proxmox connection errors"""

    pass


class ProxmoxClient:
    """Wrapper class for Proxmox API operations"""

    def __init__(self):
        """Initialize Proxmox client with environment variables"""
        self.api = ProxmoxAPI(
            host=os.getenv("PROXMOX_HOST", "localhost"),
            port=int(os.getenv("PROXMOX_PORT", "8006")),
            verify_ssl=os.getenv("PROXMOX_VERIFY_TLS", "").lower() in ["true", "1"],
            user=os.getenv("PROXMOX_USER", "example@pam"),
            token_name=os.getenv("PROXMOX_TOKEN_NAME", "proxnut"),
            token_value=os.getenv("PROXMOX_TOKEN", "******"),
            timeout=int(os.getenv("PROXMOX_TIMEOUT", "30")),
        )

    def get_nodes(self) -> List[str]:
        """Get list of available Proxmox nodes"""
        nodes_data = self.api.nodes.get() or []
        return [node["node"] for node in nodes_data]

    def shutdown_node(self, node_name: str) -> None:
        """Shutdown a specific Proxmox node"""
        self.api.nodes(node_name).status.post(command="shutdown")

    def shutdown_nodes(self, node_names: List[str]) -> Dict[str, bool]:
        """Shutdown multiple Proxmox nodes"""
        results = {}

        for node_name in node_names:
            if node_name.strip():  # Skip empty node names
                try:
                    self.shutdown_node(node_name)
                    results[node_name] = True
                except Exception:
                    results[node_name] = False

        return results

    def validate_target_nodes(self, target_nodes: List[str]) -> bool:
        """Validate that target nodes exist in Proxmox cluster"""
        available_nodes = self.get_nodes()
        target_set = set(node.strip() for node in target_nodes if node.strip())
        available_set = set(available_nodes)
        return target_set.issubset(available_set)

    def check_connection(self):
        """Check if connection to Proxmox API is successful"""
        try:
            self.api.version.get()
        except Exception:
            raise ProxmoxConnectionError("Failed to connect to Proxmox API")
