"""Opt-in integration: owns its configuration, server, panes, and registry."""

import base64
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from herdr_md.herdr import call

pytestmark = pytest.mark.skipif(
    os.environ.get("HERDR_MD_LIVE_TEST") != "1", reason="Opt-in isolated Herdr test"
)


def eventually(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError("Herdr did not reach the expected state")


def test_click_opens_new_pane_twice(monkeypatch):
    binary = os.environ.get("HERDR_MD_TEST_BINARY") or shutil.which("herdr")
    assert binary
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="hmd-") as directory:
        temp = Path(directory)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        env.update(
            XDG_CONFIG_HOME=str(temp / "config"),
            XDG_STATE_HOME=str(temp / "state"),
            XDG_CACHE_HOME=str(temp / "cache"),
            SHELL="/bin/sh",
            TERM="xterm-256color",
        )
        config = temp / "config/herdr"
        config.mkdir(parents=True)
        (config / "config.toml").write_text(
            'onboarding=false\n[terminal]\ndefault_shell="/bin/sh"\nshell_mode="non_login"\n'
        )
        subprocess.run(
            [binary, "plugin", "link", str(root)],
            env=env,
            check=True,
            capture_output=True,
            timeout=15,
        )
        session = "md-test"
        endpoint = str(config / "sessions" / session / "herdr.sock")
        monkeypatch.setenv("HERDR_SOCKET_PATH", endpoint)
        server = subprocess.Popen(
            [binary, "--session", session, "server"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            eventually(lambda: call("ping", {}))
            source = call("workspace.create", {"cwd": str(root)})["root_pane"]
            label = "Open demo.md"
            link = f"\x1b]8;;{(root / 'examples/demo.md').as_uri()}\x1b\\{label}\x1b]8;;\x1b\\"
            script = (
                "import base64;print(base64.b64decode("
                + repr(base64.b64encode(link.encode()).decode())
                + ").decode())"
            )
            call(
                "pane.send_text",
                {"pane_id": source["pane_id"], "text": "python3 -c " + shlex.quote(script) + "\n"},
            )

            def link_position():
                result = call(
                    "pane.read",
                    {"pane_id": source["pane_id"], "source": "visible", "format": "text"},
                )
                for y, line in enumerate(result["read"]["text"].splitlines()):
                    if label in line:
                        return y, line.index(label)

            for count in (2, 3):
                y, x = eventually(link_position)
                print(
                    call(
                        "pane.link.activate",
                        {"pane_id": source["pane_id"], "viewport_row": y, "col": x},
                    )
                )
                panes = eventually(
                    lambda: (
                        p
                        if len(
                            p := call("pane.list", {"workspace_id": source["workspace_id"]})[
                                "panes"
                            ]
                        )
                        == count
                        else None
                    )
                )
                assert any(p["terminal_id"] == source["terminal_id"] for p in panes)
                viewer = next(p for p in reversed(panes) if p["pane_id"] != source["pane_id"])
                eventually(
                    lambda: (
                        "Markdown Preview"
                        in call(
                            "pane.read",
                            {"pane_id": viewer["pane_id"], "source": "visible", "format": "text"},
                        )["read"]["text"]
                    )
                )
        finally:
            print("LOGS", call("plugin.log.list", {"plugin_id": "herdr-md"}))
            print("PANES", call("pane.list", {}))
            for logfile in temp.rglob("*.log"):
                print(str(logfile), logfile.read_text(errors="replace")[-4000:])
            subprocess.run(
                [binary, "--session", session, "server", "stop"],
                env=env,
                capture_output=True,
                timeout=10,
            )
            server.wait(timeout=10)
