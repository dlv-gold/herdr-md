import json
import tomllib
from pathlib import Path

import pytest

from herdr_md import cli, herdr


def test_file_url_decoding(tmp_path):
    p = tmp_path / "a # one.md"
    p.write_text("# Test")
    assert herdr.local_file(p.as_uri() + "#heading") == p


@pytest.mark.parametrize(
    "url", ["https://example.org/a.md", "file://remote.invalid/a.md", "file:///missing.md"]
)
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        herdr.local_file(url)


def test_print_link(tmp_path, capsys):
    p = tmp_path / "a b.md"
    p.write_text("text")
    assert cli.main(["--print-link", str(p)]) == 0
    output = capsys.readouterr().out
    assert "\x1b]8;;" + p.as_uri() in output
    assert "%20" in output


def test_each_action_opens_new_pane_and_preserves_source_context(tmp_path, monkeypatch):
    path = tmp_path / "test.md"
    path.write_text("test")
    monkeypatch.setenv(
        "HERDR_PLUGIN_CONTEXT_JSON",
        json.dumps({"clicked_url": path.as_uri(), "focused_pane_id": "w2:p9"}),
    )
    calls = []
    monkeypatch.setattr(herdr, "call", lambda method, params: calls.append((method, params)) or {})
    assert cli.main(["--action"]) == cli.main(["--action"]) == 0
    assert len(calls) == 2
    for method, params in calls:
        assert method == "plugin.pane.open"
        assert params["target_pane_id"] == "w2:p9"
        assert params["placement"] == "split" and params["focus"]
        assert params["env"]["HERDR_MD_FILE"] == str(path)


def test_invalid_action_does_not_open_pane(monkeypatch):
    monkeypatch.setenv(
        "HERDR_PLUGIN_CONTEXT_JSON",
        json.dumps({"clicked_url": "file:///not-found.md", "focused_pane_id": "w1:p1"}),
    )
    monkeypatch.setattr(cli, "report_error", lambda message: None)
    monkeypatch.setattr(cli, "open_pane", lambda *a: pytest.fail("Must not create an empty pane"))
    assert cli.main(["--action"]) == 1


def test_manifest_contract():
    manifest = tomllib.loads((Path(__file__).parents[1] / "herdr-plugin.toml").read_text())
    assert manifest["link_handlers"][0]["action"] == "open"
    assert manifest["panes"][0]["id"] == "viewer"


def test_sizing_refresh_targets_only_new_panes_parent():
    root = {
        "type": "split",
        "ratio": 0.6,
        "first": {"type": "pane", "pane_id": "old"},
        "second": {
            "type": "split",
            "ratio": 0.4,
            "first": {"type": "pane", "pane_id": "source"},
            "second": {"type": "pane", "pane_id": "new"},
        },
    }
    assert herdr.parent_split(root, "new") == ([True], 0.4)
    assert herdr.parent_split(root, "missing") is None


def test_socket_errors_are_reported(tmp_path, monkeypatch):
    # Missing endpoint must fail promptly, before any subprocess or pane mutation.
    monkeypatch.setenv("HERDR_SOCKET_PATH", str(tmp_path / "missing.sock"))
    with pytest.raises((OSError, ValueError)):
        herdr.call("ping", {})
