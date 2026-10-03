"""Launcher script used by PyInstaller (and handy for `python run_calviz.py`)."""

import sys

from calviz.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
