"""
Exportação de dados PPG para CSV e JSON.

Este módulo fornece funções para salvar os dados capturados
em diferentes formatos de arquivo.
"""

import json
from datetime import datetime
from typing import List, Optional

from .config import ESTIMATED_SAMPLING_RATE
from .models import PPGBlock
from .analysis import calculate_parameters


def export_csv(
    blocks: List[PPGBlock],
    raw_samples: Optional[List[int]] = None,
    filename: Optional[str] = None
) -> str:
    """
    Exporta blocos PPG para formato CSV.

    Args:
        blocks: Lista de blocos PPG
        raw_samples: Amostras brutas (fallback)
        filename: Nome do arquivo (gerado automaticamente se None)

    Returns:
        Nome do arquivo criado

    Raises:
        ValueError: Se não houver dados para exportar
    """
    total_samples = sum(len(b.samples) for b in blocks)
    if raw_samples:
        total_samples += len(raw_samples)

    if total_samples == 0:
        raise ValueError("Nenhum dado para exportar")

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ppg_data_{timestamp}.csv"

    with open(filename, 'w') as f:
        f.write("block,exam_number,label,sample_index,value\n")

        # Salvar blocos parseados
        for block_idx, block in enumerate(blocks):
            exam_str = str(block.exam_number) if block.exam_number else ""
            for sample_idx, val in enumerate(block.samples):
                f.write(f"{block_idx},{exam_str},L{block.label_char},{sample_idx},{val}\n")

        # Salvar amostras brutas (se houver)
        if raw_samples:
            for sample_idx, val in enumerate(raw_samples):
                f.write(f"raw,,raw,{sample_idx},{val}\n")

    return filename


def export_json(
    blocks: List[PPGBlock],
    raw_samples: Optional[List[int]] = None,
    filename: Optional[str] = None
) -> str:
    """
    Exporta blocos PPG para formato JSON estruturado.

    Args:
        blocks: Lista de blocos PPG
        raw_samples: Amostras brutas (fallback)
        filename: Nome do arquivo (gerado automaticamente se None)

    Returns:
        Nome do arquivo criado

    Raises:
        ValueError: Se não houver dados para exportar
    """
    if not blocks and not raw_samples:
        raise ValueError("Nenhum dado para exportar")

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ppg_data_{timestamp}.json"

    blocks_data = []
    for i, block in enumerate(blocks):
        params = calculate_parameters(block)
        block_data = {
            "index": i,
            "label": f"L{block.label_char}",
            "label_byte": block.label_byte,
            "label_desc": block.label_desc,
            "exam_number": block.exam_number,
            "timestamp": block.timestamp.isoformat(),
            "duration_seconds": block.get_duration_seconds(),
            "sample_count": len(block.samples),
            "samples": block.samples,
            "samples_ppg_percent": block.to_ppg_percent(),
            "trimmed_count": block.trimmed_count,
            "samples_raw": block.samples_raw if block.trimmed_count > 0 else None,
            "metadata_hex": block.metadata_raw.hex() if block.metadata_raw else None,
            "parameters": params.to_dict() if params else None,
        }
        blocks_data.append(block_data)

    data = {
        "export_timestamp": datetime.now().isoformat(),
        "sampling_rate_hz": ESTIMATED_SAMPLING_RATE,
        "blocks": blocks_data,
        "raw_samples": raw_samples if raw_samples else None,
    }

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

    return filename
