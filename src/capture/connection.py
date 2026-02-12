"""TCP connection management for the Vasoquant 1000.

Extracted and adapted from dppg_reader.py.
"""

import socket
import platform
import threading
import time
from typing import Optional, Callable


class TCPConnection:
    """Manages TCP connection to the Vasoquant 1000 via serial-WiFi converter."""

    SOCKET_TIMEOUT = 3.0
    CONNECT_TIMEOUT = 5.0

    # Protocol constants
    ACK = b'\x06'
    DLE = 0x10

    def __init__(self, host: str = "192.168.0.234", port: int = 1100):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self._receive_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_data: Optional[Callable[[bytes], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None

    def connect(self):
        """Connect to the device."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Enable TCP keep-alive
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            if platform.system() == 'Darwin':
                self.socket.setsockopt(socket.IPPROTO_TCP, 0x10, 5)
            elif platform.system() == 'Linux':
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2)
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except (AttributeError, OSError):
            pass

        # Disable Nagle for faster responses
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        self.socket.settimeout(self.CONNECT_TIMEOUT)
        self.socket.connect((self.host, self.port))
        self.socket.settimeout(self.SOCKET_TIMEOUT)

        self.connected = True
        self.running = True

        # Start receive thread
        self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._receive_thread.start()

    def disconnect(self):
        """Disconnect from the device."""
        self.running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

    def send(self, data: bytes):
        """Send data to the device."""
        if self.connected and self.socket:
            self.socket.send(data)

    def send_ack(self):
        """Send ACK response."""
        self.send(self.ACK)

    def _receive_loop(self):
        """Background thread: receive data from socket."""
        while self.running:
            try:
                data = self.socket.recv(1024)
                if data:
                    # Auto-ACK: respond to DLE polling and data blocks
                    if self.connected and self.socket:
                        self.socket.send(self.ACK)

                    if self.on_data:
                        self.on_data(data)
                elif data == b'':
                    # Connection closed
                    self.connected = False
                    self.running = False
                    if self.on_disconnect:
                        self.on_disconnect()
                    break
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    self.connected = False
                    self.running = False
                    if self.on_disconnect:
                        self.on_disconnect()
                break
