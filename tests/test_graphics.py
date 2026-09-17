import base64
import io
import json
import socket
import threading

from PIL import Image

from herdr_md.graphics import Graphics


def test_kitty_png_round_trip_and_owned_cleanup():
    backend = Graphics("text")
    backend.mode = "kitty"
    output = []
    backend.present(Image.new("RGBA", (8, 16), "red"), 2, 3, 1, 1, output.append)
    data = output[0]
    assert "\x1b[4;3H" in data and "q=2" in data
    payload = data.split("m=0;", 1)[1].split("\x1b\\", 1)[0]
    image = Image.open(io.BytesIO(base64.b64decode(payload)))
    assert image.getpixel((0, 0)) == (255, 0, 0, 255)
    backend.clear(output.append)
    assert f"d=I,i={backend.image_id}" in output[-1]


def test_herdr_stream_is_one_owned_layer(tmp_path, monkeypatch):
    path = str(tmp_path / "graphics.sock")
    received = []
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(path)
        server.listen()

        def accept():
            conn, _ = server.accept()
            with conn, conn.makefile("rb") as reader:
                received.append(json.loads(reader.readline()))
                conn.sendall(b'{"result":{"type":"ok"}}\n')
                header = json.loads(reader.readline())
                received.append(header)
                image = Image.open(io.BytesIO(reader.read(header["data_length"])))
                received.append(image.size)
                assert reader.read(1) == b""

        thread = threading.Thread(target=accept)
        thread.start()
        backend = Graphics("text")
        backend.mode = "herdr"
        backend.pane = "w9:p2"
        monkeypatch.setenv("HERDR_SOCKET_PATH", path)
        backend.present(Image.new("RGBA", (80, 32), "red"), 0, 1, 10, 2, lambda _: None)
        backend.clear(lambda _: None)
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert received[0]["params"]["layer_id"] == backend.layer
    assert received[0]["params"]["pane_id"] == "w9:p2"
    assert received[1]["placement"]["viewport_row"] == 1
    assert received[2] == (80, 32)
