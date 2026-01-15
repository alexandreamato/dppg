"""
D-PPG Vasoquant 1000 Reader - Modular Package

Este pacote contém os módulos para leitura e análise de dados
do aparelho de fotopletismografia digital Elcat Vasoquant 1000.
"""

from .config import ESTIMATED_SAMPLING_RATE, ADC_TO_PPG_FACTOR, LABEL_DESCRIPTIONS
from .models import PPGParameters, PPGBlock

__version__ = "1.0.0"
__all__ = [
    "ESTIMATED_SAMPLING_RATE",
    "ADC_TO_PPG_FACTOR",
    "LABEL_DESCRIPTIONS",
    "PPGParameters",
    "PPGBlock",
]
