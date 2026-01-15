#!/usr/bin/env python3
"""
Converte arquivo de captura bruta (.bin) para log legível.

Uso:
    python parse_raw_capture.py raw_capture_XXXXXX.bin
"""

import struct
import sys
from datetime import datetime

# Caracteres de controle conhecidos
CONTROL_CHARS = {
    0x00: "NUL", 0x01: "SOH", 0x02: "STX", 0x03: "ETX",
    0x04: "EOT", 0x05: "ENQ", 0x06: "ACK", 0x10: "DLE",
    0x15: "NAK", 0x1B: "ESC", 0x1D: "GS", 0x0D: "CR", 0x0A: "LF"
}


def parse_capture_file(filename):
    """Parseia arquivo de captura e imprime log legível"""

    print(f"\n{'='*70}")
    print(f"  ANÁLISE DE CAPTURA: {filename}")
    print(f"{'='*70}\n")

    first_ts = None
    total_rx = 0
    total_tx = 0

    try:
        with open(filename, "rb") as f:
            while True:
                # Ler header: [timestamp 4 bytes][direção 1 byte][tamanho 2 bytes]
                header = f.read(7)
                if len(header) < 7:
                    break

                ts, direction, length = struct.unpack('<IBH', header)

                # Ler dados
                data = f.read(length)
                if len(data) < length:
                    break

                # Calcular tempo relativo
                if first_ts is None:
                    first_ts = ts
                relative_ts = (ts - first_ts) / 1000.0

                # Direção
                if direction == 0x52:  # 'R' = RX
                    dir_str = "RX <<<"
                    total_rx += length
                    color = "\033[94m"  # Azul
                else:  # 'T' = TX
                    dir_str = "TX >>>"
                    total_tx += length
                    color = "\033[92m"  # Verde

                # Formato hex
                hex_str = " ".join(f"{b:02X}" for b in data)

                # Identificar caracteres especiais
                special = []
                for b in data:
                    if b in CONTROL_CHARS:
                        special.append(CONTROL_CHARS[b])
                special_str = f" ({', '.join(special)})" if special else ""

                # ASCII printável
                ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)

                # Reset de cor
                reset = "\033[0m"

                # Imprimir
                print(f"[{relative_ts:8.3f}s] {color}{dir_str}{reset} [{length:4d}] {hex_str}{special_str}")
                if len(ascii_str.replace(".", "")) > 3:
                    print(f"             ASCII: {ascii_str}")

    except FileNotFoundError:
        print(f"Erro: Arquivo '{filename}' não encontrado!")
        return
    except Exception as e:
        print(f"Erro ao ler arquivo: {e}")
        return

    print(f"\n{'='*70}")
    print(f"  RESUMO")
    print(f"{'='*70}")
    print(f"  Total RX (recebido): {total_rx:,} bytes")
    print(f"  Total TX (enviado):  {total_tx:,} bytes")
    print(f"{'='*70}\n")


def main():
    if len(sys.argv) < 2:
        print("Uso: python parse_raw_capture.py <arquivo.bin>")
        print("\nArquivos de captura disponíveis:")
        import glob
        for f in glob.glob("raw_capture_*.bin"):
            print(f"  {f}")
        return

    parse_capture_file(sys.argv[1])


if __name__ == "__main__":
    main()
