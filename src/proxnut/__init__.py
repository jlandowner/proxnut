"""proxnut - Proxmox UPS Shutdown Tool

This is the package initialization file (__init__.py):
- Makes this directory a Python package
- Executed when 'import proxnut' is called
- Defines the public API for the package
- Used by pyproject.toml [project.scripts] entry point: proxnut = "proxnut:main"
- Enables 'uv run proxnut' command
"""

__version__ = "0.0.1-r1"

from .proxnut import main

__all__ = ["main"]