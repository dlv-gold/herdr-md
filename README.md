# Herdr MD

Ctrl-click a local Markdown file hyperlink in Herdr to open a **new focused split** with live Markdown, LaTeX and PNG previews. The same viewer runs directly in Kitty.

## Install with Herdr

Requires Linux, Python 3.12+ (available as `python3`, with `venv` support), Kitty, and Herdr 0.9.0 or newer.

```sh
herdr plugin install dlv-gold/herdr-md
```

Review and accept Herdr's installation prompt. Herdr downloads the plugin, runs its bootstrap to create a private Python environment, and registers the plugin. No manual clone or `pip install` is needed. Dependencies are downloaded during installation; viewing local documents works offline.

Open the file picker in a new pane:

```sh
herdr plugin action invoke herdr-md.open
```

Choose a Markdown file, or press `o` in the viewer to open another. Enable graphics in Herdr's configuration for equations and figures:

```toml
[terminal]
kitty_graphics = true
```

The Herdr installation does not add `herdr-md` to your shell's PATH. The optional standalone CLI setup is described below.

Uninstall with:

```sh
herdr plugin uninstall herdr-md
```

## Click a Markdown link

With the optional standalone CLI installed (see below), print a terminal hyperlink inside a Herdr shell pane:

```sh
herdr-md --print-link /path/to/report.md
```

**Ctrl-click the resulting link.** Each activation opens a new split beside the source pane. This also works with matching OSC 8 `file://` hyperlinks emitted by other terminal applications. On stock Herdr 0.9.0, plain Markdown filenames without hyperlink metadata are not recognized by this plugin. Use Herdr's Ctrl-click gesture so Herdr can route the link to the plugin.

Run the link-printing command at a shell prompt in Herdr and click its output. Links displayed in a separate chat interface are handled by that interface. If clicking fails, `herdr-md --pane /path/to/report.md` opens the preview directly.

Percent-encoded filenames, spaces and local-host file URLs are supported. URL fragments are accepted; the initial preview opens at the document start. Remote-host file URLs and web downloads are outside this version's scope.

Inside the preview, click another local Markdown link to open it in a new Herdr pane. Standalone mode loads the target in the existing viewer.

## Reading

| Key | Action |
| --- | --- |
| Arrows / Page Up / Page Down / Home / End | Scroll |
| `/`, then Enter | Search text |
| `n` | Next match |
| `o` | Open a file |
| `r` | Refresh |
| Escape | Close search or cancel picker |
| `q` | Quit this viewer |

Prose is terminal text and supports Textual's mouse selection. Equations and figures are images; their pixels are not selectable text. Rendering uses a dark background for readable mathematical glyphs and transparent figures.

Use `$...$` for inline math and `$$...$$` for display math. Common mathematical LaTeX includes fractions, roots, scripts, Greek letters, sums, integrals, and matrices. Ziamath/latex2mathml provide a mathematical subset, not a full TeX engine with arbitrary packages or macros. Code fences and inline code keep dollar signs literal. Unsupported expressions show source when the renderer reports an error.

Use ordinary Markdown image references, such as `![Caption](figures/result.png)`. PNG paths resolve relative to the document. Figures preserve their aspect ratio and fit the pane. The document and referenced figures update automatically after saves, including atomic replacements. Use `--no-watch` for manual refresh.

In terminals without graphics, or with `--graphics=text`, equations remain readable LaTeX and images have text descriptions. Inside Herdr, the viewer uses an owned pane graphics layer. `[terminal].kitty_graphics` must be enabled for images; configuration changes can require a Herdr restart, which this plugin never performs automatically.

Optional keybinding in Herdr's configuration:

```toml
[[keys.command]]
key = "prefix+m"
type = "plugin_action"
command = "herdr-md.open"
description = "open Markdown preview"
```

## Optional standalone CLI and local development

For the standalone `herdr-md` command, or to work on the plugin locally:

```sh
git clone https://github.com/dlv-gold/herdr-md.git
cd herdr-md
python3 scripts/bootstrap.py
mkdir -p ~/.local/bin
ln -s "$PWD/.venv/bin/herdr-md" ~/.local/bin/herdr-md
```

Ensure `~/.local/bin` is on your PATH and keep the checkout at this location. Alternatively, use `.venv/bin/herdr-md` directly.

```sh
herdr-md /path/to/report.md          # current terminal
herdr-md --pane /path/to/report.md   # new Herdr split
herdr-md                            # file picker
```

To use this checkout as the Herdr plugin during development, run `herdr plugin link "$PWD"`. Unlink it with `herdr plugin unlink herdr-md`; the source checkout and documents remain available.

## Development and verification

```sh
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m build --no-isolation
HERDR_MD_LIVE_TEST=1 .venv/bin/pytest tests/test_live_herdr.py -q
```

The opt-in live test creates its own registry, config, named server and panes, activates a real OSC 8 file link twice, and checks that each activation opens another viewer. It stops only its own server. Headless tests cannot certify GPU rendering: the demo should also be exercised in Kitty and Herdr after changes to the graphics transport.


## License

MIT. See [LICENSE](LICENSE).
