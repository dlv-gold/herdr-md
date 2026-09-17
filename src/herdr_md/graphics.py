"""Owned viewport graphics. Never delete another application's images."""

import base64
import fcntl
import io
import json
import os
import random
import select
import socket
import struct
import termios
import time
import tty

from PIL import Image

from .herdr import call


class Graphics:
    def __init__(self, mode="auto"):
        self.mode = "text"
        self.cell = (8, 16)
        self.pane = os.environ.get("HERDR_PANE_ID")
        self.stream = None
        self.image_id = random.randint(1, 2**31)
        self.layer = f"herdr-md-{os.getpid()}"
        self.error = ""
        if mode == "text":
            return
        try:
            if os.environ.get("HERDR_ENV") == "1" and self.pane:
                for _ in range(5):
                    info = call("pane.graphics.info", {"pane_id": self.pane})
                    if info["cell_width_px"] and info["cell_height_px"]:
                        self.cell = info["cell_width_px"], info["cell_height_px"]
                        self.mode = "herdr"
                        break
                    time.sleep(0.1)
            elif os.isatty(1) and self.probe_kitty():
                self.mode = "kitty"
                self.measure()
        except (OSError, ValueError, KeyError) as exc:
            self.error = str(exc)

    def probe_kitty(self):
        # Probe before Textual takes ownership of input.
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        saved = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            os.write(fd, b"\x1b_Gi=314159,a=q,t=d,f=24,s=1,v=1;AAAA\x1b\\")
            reply = b""
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                if select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
                    reply += os.read(fd, 4096)
                    if b"i=314159;OK" in reply:
                        return True
            return False
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, saved)
            os.close(fd)

    def measure(self):
        if self.mode == "herdr":
            info = call("pane.graphics.info", {"pane_id": self.pane})
            if info["cell_width_px"] and info["cell_height_px"]:
                self.cell = info["cell_width_px"], info["cell_height_px"]
        elif self.mode == "kitty":
            rows, cols, width, height = struct.unpack(
                "HHHH", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 8)
            )
            if rows and cols and width and height:
                self.cell = max(1, width // cols), max(1, height // rows)
        return self.cell

    def present(self, image: Image.Image, x: int, y: int, cols: int, rows: int, write):
        if self.mode == "text" or cols <= 0 or rows <= 0:
            return
        data = io.BytesIO()
        image.save(data, format="PNG")
        payload = data.getvalue()
        if self.mode == "herdr":
            if self.stream is None:
                self.stream = socket.socket(socket.AF_UNIX)
                self.stream.settimeout(2)
                self.stream.connect(os.environ["HERDR_SOCKET_PATH"])
                request = {
                    "id": "graphics",
                    "method": "pane.graphics.stream",
                    "params": {"pane_id": self.pane, "layer_id": self.layer, "z_index": 1},
                }
                self.stream.sendall((json.dumps(request) + "\n").encode())
                reply = bytearray()
                while not reply.endswith(b"\n"):
                    byte = self.stream.recv(1)
                    if not byte or len(reply) > 65536:
                        raise ValueError("Graphics stream disconnected")
                    reply.extend(byte)
                if "error" in json.loads(reply):
                    raise ValueError("Herdr could not open the graphics layer")
            header = {
                "format": "png",
                "image_width": image.width,
                "image_height": image.height,
                "data_length": len(payload),
                "placement": {
                    "viewport_col": x,
                    "viewport_row": y,
                    "grid_cols": cols,
                    "grid_rows": rows,
                },
            }
            self.stream.sendall((json.dumps(header) + "\n").encode() + payload)
        else:
            encoded = base64.b64encode(payload).decode()
            parts = ["\x1b7", f"\x1b[{y + 1};{x + 1}H"]
            for start in range(0, len(encoded), 4096):
                chunk = encoded[start : start + 4096]
                more = int(start + 4096 < len(encoded))
                control = (
                    f"a=T,f=100,t=d,i={self.image_id},p=1,q=2,C=1,c={cols},r={rows},z=1,"
                    if start == 0
                    else "q=2,"
                )
                parts.append(f"\x1b_G{control}m={more};{chunk}\x1b\\")
            parts.append("\x1b8")
            write("".join(parts))

    def clear(self, write):
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.mode == "kitty":
            write(f"\x1b_Ga=d,d=I,i={self.image_id},q=2\x1b\\")
