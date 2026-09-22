"""Small bounded socket client and explicit pane launcher."""

import json
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


def local_file(url: str) -> Path:
    parsed = urlsplit(url)
    if parsed.scheme != "file" or parsed.netloc not in {
        "",
        "localhost",
        socket.gethostname(),
        socket.getfqdn(),
    }:
        raise ValueError("Expected a local file:// Markdown or PNG link")
    return checked_file(Path(unquote(parsed.path)))


def checked_file(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.suffix.lower() not in {".md", ".markdown", ".png"}:
        raise ValueError("Select a .md, .markdown or .png file")
    if not path.is_file():
        raise ValueError(f"Preview file not found: {path}")
    with path.open("rb") as source:
        source.read(1)
    return path


def call(method: str, params: dict) -> dict:
    endpoint = os.environ.get("HERDR_SOCKET_PATH")
    if not endpoint:
        raise ValueError("This operation needs a Herdr pane")
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5)
        sock.connect(endpoint)
        sock.sendall(
            (json.dumps({"id": "herdr-md", "method": method, "params": params}) + "\n").encode()
        )
        with sock.makefile("rb") as reader:
            raw = reader.readline(4 * 1024 * 1024)
    response = json.loads(raw)
    if "error" in response:
        raise ValueError(response["error"].get("message", str(response["error"])))
    return response["result"]


def open_pane(path: Path | None, context: dict | None = None) -> dict:
    context = context or {}
    pane = context.get("focused_pane_id") or os.environ.get("HERDR_PANE_ID")
    if not pane:
        raise ValueError("Open the preview from a Herdr pane")
    cwd = (
        str(path.parent)
        if path
        else context.get("focused_pane_cwd") or context.get("workspace_cwd") or os.getcwd()
    )
    result = call(
        "plugin.pane.open",
        {
            "plugin_id": "herdr-md",
            "entrypoint": "viewer",
            "placement": "split",
            "target_pane_id": pane,
            "direction": "right",
            "focus": True,
            "cwd": cwd,
            "env": {"HERDR_MD_FILE": str(path) if path else "", "HERDR_MD_DIRECTORY": cwd},
        },
    )
    # Herdr 0.9.0 can initially leave a new plugin PTY at the whole-tab size.
    # Reapply only the newly created split's existing ratio to synchronize it.
    opened = result.get("plugin_pane", {}).get("pane")
    if opened:
        try:
            layout = call("layout.export", {"tab_id": opened["tab_id"]})["layout"]
            split = parent_split(layout["root"], opened["pane_id"])
            if split:
                split_path, ratio = split
                call(
                    "layout.set_split_ratio",
                    {"tab_id": opened["tab_id"], "path": split_path, "ratio": ratio},
                )
        except (OSError, ValueError, KeyError) as exc:
            report_error(f"Preview opened, but pane sizing could not synchronize: {exc}")
    return result


def parent_split(node: dict, pane_id: str, path: list[bool] | None = None):
    path = [] if path is None else path
    if node.get("type") != "split":
        return None
    for side, key in ((False, "first"), (True, "second")):
        child = node[key]
        if child.get("type") == "pane" and child.get("pane_id") == pane_id:
            return path, node["ratio"]
        if found := parent_split(child, pane_id, [*path, side]):
            return found
    return None


def report_error(message: str) -> None:
    try:
        subprocess.run(
            [
                os.environ.get("HERDR_BIN_PATH", "herdr"),
                "notification",
                "show",
                "Markdown preview",
                "--body",
                message,
            ],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
