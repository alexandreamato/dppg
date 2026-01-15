#!/usr/bin/env python3
"""
D-PPG Vasoquant 1000 Reader

Aplicativo para leitura de dados do aparelho de fotopletismografia
digital (D-PPG) Elcat Vasoquant 1000.

Uso:
    python main.py

Requisitos:
    - Python 3.8+
    - numpy
    - tkinter (geralmente incluído no Python)
"""

from src.ui import DPPGReaderApp


def main():
    """Ponto de entrada principal."""
    app = DPPGReaderApp()
    app.run()


if __name__ == "__main__":
    main()
