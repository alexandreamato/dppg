#!/usr/bin/env python3
"""
Serial Sniffer para Vasoquant 1000
Intercepta comunicação entre o aparelho e o software original no Windows.

MODOS DE OPERAÇÃO:

1. MODO PROXY (recomendado):
   - Requer com0com ou similar para criar par de portas virtuais
   - Aparelho conecta em COM_REAL (ex: COM2)
   - Software original conecta na porta virtual (ex: COM10)
   - Script faz ponte entre eles logando tudo

2. MODO PASSIVO:
   - Apenas escuta uma porta e loga tudo que chega
   - Útil para capturar dados do aparelho diretamente

USO NO WINDOWS:
   1. Instale Python 3 e pyserial: pip install pyserial
   2. Para modo proxy, instale com0com: https://sourceforge.net/projects/com0com/
      - Crie par: COM10 <-> COM11
      - Configure Vasoview para usar COM10
      - Execute: python serial_sniffer.py --proxy COM2 COM11
   3. Para modo passivo:
      - Execute: python serial_sniffer.py --listen COM2

SAÍDA:
   - Log no console com timestamp e direção
   - Arquivo .log com dados brutos em hex
   - Arquivo .bin com dados binários brutos
"""

import serial
import serial.tools.list_ports
import sys
import os
import time
import threading
import argparse
from datetime import datetime
from queue import Queue


class SerialSniffer:
    def __init__(self, log_dir="."):
        self.log_dir = log_dir
        self.running = False
        self.start_time = None

        # Criar nome base para arquivos de log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_base = os.path.join(log_dir, f"serial_capture_{timestamp}")

        # Arquivos de log
        self.log_file = None
        self.bin_file_rx = None
        self.bin_file_tx = None

    def _open_logs(self):
        """Abre arquivos de log"""
        self.log_file = open(f"{self.log_base}.log", "w", encoding="utf-8")
        self.bin_file_rx = open(f"{self.log_base}_rx.bin", "wb")
        self.bin_file_tx = open(f"{self.log_base}_tx.bin", "wb")

        self.log_file.write(f"=== Serial Capture iniciado em {datetime.now().isoformat()} ===\n\n")
        self.log_file.flush()

    def _close_logs(self):
        """Fecha arquivos de log"""
        if self.log_file:
            self.log_file.write(f"\n=== Capture finalizado em {datetime.now().isoformat()} ===\n")
            self.log_file.close()
        if self.bin_file_rx:
            self.bin_file_rx.close()
        if self.bin_file_tx:
            self.bin_file_tx.close()

    def _log(self, direction, data, port_name=""):
        """Loga dados recebidos/enviados"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        timestamp = f"[{elapsed:10.3f}s]"

        # Formato hex
        hex_str = " ".join(f"{b:02X}" for b in data)

        # Identificar bytes especiais
        special = []
        control_chars = {
            0x00: "NUL", 0x01: "SOH", 0x02: "STX", 0x03: "ETX",
            0x04: "EOT", 0x05: "ENQ", 0x06: "ACK", 0x10: "DLE",
            0x15: "NAK", 0x1B: "ESC", 0x1D: "GS", 0x0D: "CR", 0x0A: "LF"
        }
        for b in data:
            if b in control_chars:
                special.append(control_chars[b])
        special_str = f" ({', '.join(special)})" if special else ""

        # ASCII printável
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)

        # Log para console
        arrow = ">>>" if direction == "TX" else "<<<"
        color_start = "\033[92m" if direction == "TX" else "\033[94m"  # Verde TX, Azul RX
        color_end = "\033[0m"

        # No Windows, cores ANSI podem não funcionar, então verificamos
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except:
                color_start = ""
                color_end = ""

        print(f"{timestamp} {color_start}{direction} {arrow}{color_end} [{len(data):3d}] {hex_str}{special_str}")
        if len(ascii_str.replace(".", "")) > 3:  # Se tem texto legível
            print(f"             ASCII: {ascii_str}")

        # Log para arquivo
        if self.log_file:
            self.log_file.write(f"{timestamp} {direction} {port_name} [{len(data):3d}] {hex_str}{special_str}\n")
            if len(ascii_str.replace(".", "")) > 3:
                self.log_file.write(f"             ASCII: {ascii_str}\n")
            self.log_file.flush()

        # Log binário
        if direction == "RX" and self.bin_file_rx:
            self.bin_file_rx.write(data)
            self.bin_file_rx.flush()
        elif direction == "TX" and self.bin_file_tx:
            self.bin_file_tx.write(data)
            self.bin_file_tx.flush()

    def list_ports(self):
        """Lista portas seriais disponíveis"""
        print("\nPortas seriais disponíveis:")
        print("-" * 50)
        ports = serial.tools.list_ports.comports()
        if not ports:
            print("  Nenhuma porta encontrada!")
        for port in ports:
            print(f"  {port.device}: {port.description}")
        print("-" * 50)
        print()

    def listen_mode(self, port, baudrate=9600, auto_ack=True):
        """
        Modo passivo: apenas escuta uma porta.
        """
        print(f"\n{'='*60}")
        print(f"MODO PASSIVO - Escutando {port} @ {baudrate} baud")
        print(f"Auto-ACK: {'Sim' if auto_ack else 'Não'}")
        print(f"{'='*60}")
        print("Pressione Ctrl+C para parar\n")

        self._open_logs()
        self.start_time = time.time()
        self.running = True

        try:
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                rtscts=False,
                dsrdtr=False
            )
            print(f"Porta {port} aberta com sucesso!\n")

            while self.running:
                data = ser.read(1024)
                if data:
                    self._log("RX", data, port)
                    # Auto-responder ACK para manter dispositivo feliz
                    if auto_ack:
                        ser.write(b'\x06')
                        self._log("TX", b'\x06', port)

        except serial.SerialException as e:
            print(f"Erro ao abrir porta {port}: {e}")
        except KeyboardInterrupt:
            print("\n\nInterrompido pelo usuário")
        finally:
            self.running = False
            self._close_logs()
            try:
                ser.close()
            except:
                pass
            print(f"\nLogs salvos em: {self.log_base}.*")

    def proxy_mode(self, device_port, app_port, baudrate=9600):
        """
        Modo proxy: faz ponte entre dispositivo e aplicativo.

        device_port: porta onde o Vasoquant está conectado (ex: COM2)
        app_port: porta virtual onde o Vasoview conecta (ex: COM11)
        """
        print(f"\n{'='*60}")
        print(f"MODO PROXY - Interceptando comunicação")
        print(f"{'='*60}")
        print(f"  Dispositivo: {device_port}")
        print(f"  Aplicativo:  {app_port}")
        print(f"  Baudrate:    {baudrate}")
        print(f"{'='*60}")
        print("Pressione Ctrl+C para parar\n")

        self._open_logs()
        self.start_time = time.time()
        self.running = True

        ser_device = None
        ser_app = None

        try:
            # Abrir porta do dispositivo (Vasoquant)
            ser_device = serial.Serial(
                port=device_port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05
            )
            print(f"Porta do dispositivo {device_port} aberta!")

            # Abrir porta do aplicativo (virtual)
            ser_app = serial.Serial(
                port=app_port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05
            )
            print(f"Porta do aplicativo {app_port} aberta!")
            print("\nPronto para interceptar. Inicie o Vasoview...\n")

            while self.running:
                # Dados do dispositivo -> aplicativo
                data = ser_device.read(1024)
                if data:
                    self._log("RX", data, f"{device_port}->APP")
                    ser_app.write(data)

                # Dados do aplicativo -> dispositivo
                data = ser_app.read(1024)
                if data:
                    self._log("TX", data, f"APP->{device_port}")
                    ser_device.write(data)

        except serial.SerialException as e:
            print(f"Erro de porta serial: {e}")
        except KeyboardInterrupt:
            print("\n\nInterrompido pelo usuário")
        finally:
            self.running = False
            self._close_logs()
            if ser_device:
                try:
                    ser_device.close()
                except:
                    pass
            if ser_app:
                try:
                    ser_app.close()
                except:
                    pass
            print(f"\nLogs salvos em: {self.log_base}.*")


def main():
    parser = argparse.ArgumentParser(
        description="Serial Sniffer para Vasoquant 1000",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  Listar portas disponíveis:
    python serial_sniffer.py --list

  Modo passivo (escutar COM2):
    python serial_sniffer.py --listen COM2

  Modo proxy (interceptar entre COM2 e COM11):
    python serial_sniffer.py --proxy COM2 COM11

Configuração do modo proxy no Windows:
  1. Instale com0com: https://sourceforge.net/projects/com0com/
  2. Crie um par de portas virtuais: COM10 <-> COM11
  3. Configure o Vasoview para usar COM10
  4. Execute: python serial_sniffer.py --proxy COM2 COM11
  5. Inicie o Vasoview e exporte exames
        """
    )

    parser.add_argument("--list", "-l", action="store_true",
                        help="Listar portas seriais disponíveis")
    parser.add_argument("--listen", "-L", metavar="PORT",
                        help="Modo passivo: escutar uma porta")
    parser.add_argument("--proxy", "-p", nargs=2, metavar=("DEVICE", "APP"),
                        help="Modo proxy: DEVICE=porta do Vasoquant, APP=porta virtual")
    parser.add_argument("--baud", "-b", type=int, default=9600,
                        help="Baudrate (padrão: 9600)")
    parser.add_argument("--output", "-o", default=".",
                        help="Diretório para salvar logs (padrão: atual)")
    parser.add_argument("--no-ack", action="store_true",
                        help="Não responder ACK automaticamente (modo passivo)")

    args = parser.parse_args()

    sniffer = SerialSniffer(log_dir=args.output)

    if args.list:
        sniffer.list_ports()
    elif args.listen:
        sniffer.listen_mode(args.listen, args.baud, auto_ack=not args.no_ack)
    elif args.proxy:
        sniffer.proxy_mode(args.proxy[0], args.proxy[1], args.baud)
    else:
        # Se nenhum argumento, mostrar ajuda e listar portas
        parser.print_help()
        sniffer.list_ports()


if __name__ == "__main__":
    main()
