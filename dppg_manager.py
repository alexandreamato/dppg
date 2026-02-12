#!/usr/bin/env python3
"""
D-PPG Manager - Vasoquant 1000
Gerenciamento de exames, laudos e pacientes para fotopletismografia digital.
"""

import sys
import os

# Ensure src/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from src.gui.app import DPPGManagerApp


def main():
    app = DPPGManagerApp()
    app.run()


if __name__ == "__main__":
    main()
