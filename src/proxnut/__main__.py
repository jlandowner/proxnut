"""Entry point for running proxnut as a module

This is the module execution file (__main__.py):
- Executed when 'python -m proxnut' is called
- Provides alternative way to run without uv
- Different from __init__.py which handles 'import proxnut' and 'uv run proxnut'
- Both files call the same main() function but through different paths

Usage:
  python -m proxnut    # Uses this __main__.py file
  uv run proxnut       # Uses __init__.py through pyproject.toml entry point
"""

from .proxnut import main

if __name__ == "__main__":
    main()