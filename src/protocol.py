"""
Parser do protocolo de comunicação do Vasoquant 1000.

Este módulo implementa a decodificação do protocolo serial
usado pelo Vasoquant para enviar dados PPG.

Formato do protocolo:
    ESC (0x1B) + 'L' (0x4C) + label + EOT + SOH + GS + size + dados + metadados
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass

from .config import Protocol, ESTIMATED_SAMPLING_RATE
from .models import PPGBlock


@dataclass
class ParseResult:
    """Resultado do parsing de um bloco."""
    block: Optional[PPGBlock]
    bytes_consumed: int
    needs_more_data: bool


def parse_buffer(buffer: bytearray) -> Tuple[List[PPGBlock], bytearray]:
    """
    Parseia o buffer procurando blocos PPG completos.

    Args:
        buffer: Buffer com dados recebidos

    Returns:
        Tupla (lista de blocos encontrados, buffer restante)
    """
    blocks = []
    remaining = buffer

    while True:
        result = _try_parse_block(remaining)

        if result.needs_more_data:
            break

        if result.block:
            blocks.append(result.block)

        remaining = remaining[result.bytes_consumed:]

        if result.bytes_consumed == 0:
            break

    return blocks, remaining


def _try_parse_block(buffer: bytearray) -> ParseResult:
    """
    Tenta parsear um bloco do início do buffer.

    Args:
        buffer: Buffer com dados

    Returns:
        ParseResult com o bloco (se encontrado) e bytes consumidos
    """
    # Procurar início de bloco: ESC (0x1B)
    try:
        esc_pos = buffer.index(Protocol.ESC)
    except ValueError:
        return ParseResult(None, len(buffer), False)

    # Verificar bytes suficientes para header
    if esc_pos + 10 > len(buffer):
        return ParseResult(None, 0, True)

    # Verificar formato válido: ESC + 'L' + label + EOT + SOH + GS
    if not _is_valid_header(buffer, esc_pos):
        # Não é bloco válido, pular o ESC
        return ParseResult(None, esc_pos + 1, False)

    label_byte = buffer[esc_pos + 2]

    # Extrair tamanho (bytes 7 e 8, little-endian)
    size_low = buffer[esc_pos + 7]
    size_high = buffer[esc_pos + 8]
    num_samples = size_low | (size_high << 8)

    # Calcular posição dos dados
    data_start = esc_pos + 9
    data_end = data_start + (num_samples * 2)

    # Verificar se temos todos os dados
    if data_end > len(buffer):
        return ParseResult(None, 0, True)

    # Verificar se há metadados ou próximo bloco
    metadata_min_size = 10
    has_next_block = _has_next_block(buffer, data_end)

    if not has_next_block and (data_end + metadata_min_size) > len(buffer):
        return ParseResult(None, 0, True)

    # Extrair amostras (16-bit little-endian)
    samples = _extract_samples(buffer, data_start, data_end)

    # Capturar metadados
    metadata_start = data_end
    metadata_end = min(metadata_start + 40, len(buffer))
    metadata_raw = bytes(buffer[metadata_start:metadata_end])

    # Extrair número do exame e payload dos metadados
    exam_number, payload_start = _extract_exam_number(metadata_raw)

    # Extrair baseline (bytes 1-2 após primeiro GS)
    hw_baseline = None
    if len(metadata_raw) >= 3 and metadata_raw[0] == Protocol.GS:
        hw_baseline = metadata_raw[1] | (metadata_raw[2] << 8)

    # Criar bloco
    block = PPGBlock(label_byte, samples, exam_number, metadata_raw)

    # Preencher valores do hardware a partir do payload
    if hw_baseline is not None:
        block.hw_baseline = hw_baseline

    if payload_start is not None and payload_start + 10 <= len(metadata_raw):
        _extract_hw_metadata(block, metadata_raw[payload_start:])

    # Calcular bytes consumidos (até próximo ESC ou fim dos metadados)
    next_start = _find_next_block_start(buffer, data_end)

    return ParseResult(block, next_start, False)


def _is_valid_header(buffer: bytearray, pos: int) -> bool:
    """Verifica se a posição contém um header de bloco válido."""
    return (
        buffer[pos + 1] == 0x4C and      # 'L'
        buffer[pos + 3] == Protocol.EOT and
        buffer[pos + 4] == Protocol.SOH and
        buffer[pos + 5] == Protocol.GS
    )


def _has_next_block(buffer: bytearray, start: int) -> bool:
    """Verifica se há um próximo bloco após a posição dada."""
    for i in range(start, min(start + 30, len(buffer))):
        if buffer[i] == Protocol.ESC:
            return True
    return False


def _extract_samples(buffer: bytearray, start: int, end: int) -> List[int]:
    """Extrai amostras 16-bit little-endian do buffer."""
    samples = []
    for i in range(start, end, 2):
        if i + 1 < len(buffer):
            low = buffer[i]
            high = buffer[i + 1]
            value = low | (high << 8)
            samples.append(value)
    return samples


def _extract_exam_number(metadata: bytes) -> Tuple[Optional[int], Optional[int]]:
    """
    Extrai o número do exame dos metadados.

    Padrão observado: 00 00 00 GS LL HH [payload...]
    onde HHLL é o número do exame em little-endian.

    Returns:
        Tupla (exam_number, payload_start_index) ou (None, None)
    """
    for i in range(len(metadata) - 5):
        if (metadata[i] == 0x00 and
            metadata[i + 1] == 0x00 and
            metadata[i + 2] == 0x00 and
            metadata[i + 3] == Protocol.GS):

            exam_low = metadata[i + 4]
            exam_high = metadata[i + 5]
            exam_number = exam_low | (exam_high << 8)

            # Validar: números típicos são 1-9999
            if 1 <= exam_number <= 9999:
                return exam_number, i + 6

    return None, None


def _extract_hw_metadata(block: PPGBlock, payload: bytes) -> None:
    """
    Extrai parâmetros calculados pelo hardware do payload de metadados.

    Formato do payload (10 bytes, verificado em 32 blocos):
        Byte 0:    To_samples (end_index - peak_index, em amostras)
        Byte 1:    Th_samples (amostras até 50% recuperação)
        Bytes 2-3: amplitude (16-bit LE, peak - baseline, ADC)
        Bytes 4-5: Fo × 100 (16-bit LE, em 0.01 %·s)
        Byte 6:    peak_raw (peak_index = peak_raw + 2×sr - 1)
        Byte 7:    Ti (segundos, inteiro)
        Byte 8:    flags (0x00=normal, 0x80=sem endpoint)
        Byte 9:    0x04 (EOT)

    Args:
        block: Bloco PPG para preencher
        payload: Bytes do payload (a partir de após exam_number)
    """
    sr = int(ESTIMATED_SAMPLING_RATE)

    block.hw_To_samples = payload[0]
    block.hw_Th_samples = payload[1]
    block.hw_amplitude = payload[2] | (payload[3] << 8)
    block.hw_Fo_x100 = payload[4] | (payload[5] << 8)

    peak_raw = payload[6]
    block.hw_peak_index = peak_raw + 2 * sr - 1  # peak_raw + 7

    block.hw_Ti = payload[7]
    block.hw_flags = payload[8]

    # Calcular end_index
    block.hw_end_index = block.hw_peak_index + block.hw_To_samples


def _find_next_block_start(buffer: bytearray, start: int) -> int:
    """Encontra o início do próximo bloco ou fim dos dados."""
    pos = start
    while pos < len(buffer) and buffer[pos] != Protocol.ESC:
        pos += 1
    return pos
