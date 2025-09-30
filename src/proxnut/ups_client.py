"""UPS client wrapper"""

import os
from typing import List, Dict, Any
from PyNUTClient import PyNUT


class UPSStatusNotNormalError(Exception):
    """Custom exception for non-normal UPS status"""

    def __init__(self, status: str):
        self.status = status
        super().__init__(f"UPS status is not normal: {status}")


class UPSClient:
    """Wrapper class for NUT (Network UPS Tools) operations"""

    def __init__(self):
        """Initialize UPS client with environment variables"""
        self.host = os.getenv("NUT_HOST", "localhost")
        self.port = int(os.getenv("NUT_PORT", "3493"))
        self.ups_name = os.getenv("NUT_UPS_NAME", "")
        self.normal_statuses = os.getenv("UPS_NORMAL_STATUSES", "OL,OL CHRG").split(",")

        self.client = PyNUT.PyNUTClient(host=self.host, port=self.port)

    def get_ups_names(self) -> List[str]:
        """Get list of available UPS names from NUT server"""
        return self.client.GetUPSNames()

    def validate_ups_name(self) -> bool:
        """Validate that configured UPS name exists"""
        if not self.ups_name:
            return False

        available_names = self.get_ups_names()
        return self.ups_name in available_names

    def decode_if_bytes(self, obj: Any) -> str:
        """Decode bytes to string if needed"""
        if isinstance(obj, bytes):
            return obj.decode("utf-8")
        return str(obj)

    def get_ups_variables(self) -> Dict[str, str]:
        """Get all UPS variables"""
        ups_vars = self.client.GetUPSVars(self.ups_name)
        # Decode all values to strings
        return {
            self.decode_if_bytes(k): self.decode_if_bytes(v)
            for k, v in ups_vars.items()
        }

    def get_ups_status(self) -> str:
        """Get current UPS status"""
        ups_vars = self.get_ups_variables()
        return ups_vars.get("ups.status", "")

    def check_ups_status_normal(self):
        """Check if UPS status is normal"""
        status = self.get_ups_status()
        if status not in self.normal_statuses:
            raise UPSStatusNotNormalError(status)
