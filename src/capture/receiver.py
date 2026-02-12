"""Data reception and protocol parsing for the Vasoquant 1000.

Extracted from dppg_reader.py. Uses src/protocol.py for block parsing.
"""

import threading
from typing import List, Callable, Optional

from ..protocol import parse_buffer
from ..models import PPGBlock


class DataReceiver:
    """Receives data from connection and parses PPG blocks."""

    def __init__(self):
        self.buffer = bytearray()
        self.blocks: List[PPGBlock] = []
        self._lock = threading.Lock()

        # Callbacks
        self.on_block: Optional[Callable[[PPGBlock], None]] = None

    def feed(self, data: bytes):
        """Feed raw data from connection into the parser.

        This is called from the connection's on_data callback.
        Thread-safe.
        """
        with self._lock:
            self.buffer.extend(data)
            new_blocks, self.buffer = parse_buffer(self.buffer)
            for block in new_blocks:
                self.blocks.append(block)
                if self.on_block:
                    self.on_block(block)

    def clear(self):
        """Clear all received data."""
        with self._lock:
            self.buffer.clear()
            self.blocks.clear()

    def get_blocks(self) -> List[PPGBlock]:
        """Return a copy of all received blocks."""
        with self._lock:
            return list(self.blocks)

    def flush_buffer(self):
        """Force parse any remaining data in buffer."""
        with self._lock:
            if self.buffer:
                new_blocks, self.buffer = parse_buffer(self.buffer)
                for block in new_blocks:
                    self.blocks.append(block)
                    if self.on_block:
                        self.on_block(block)
