# Herdr MD

A Markdown preview plugin for [Herdr](https://herdr.dev), with rendered LaTeX equations, local PNG figures, and live refresh. Open a document in a terminal pane beside your editor or coding agent and see changes as you save.

The viewer keeps prose as selectable terminal text and renders equations and figures as images. It also runs as a standalone terminal application in Kitty.

## Features

- Read local `.md` and `.markdown` files in a new Herdr split.
- Render inline `$...$` and display `$$...$$` mathematical LaTeX.
- Display local PNG figures referenced by the document.
- Refresh when the Markdown file or its referenced figures change.
- Scroll, search text, and choose files from the viewer.
- Follow links to other Markdown documents in new Herdr panes.

## Install with Herdr

Requires Linux, Herdr 0.9.0 or newer, and Python 3.12+ available as `python3` with `venv` support. Kitty is the tested terminal for graphics; text-only fallback is available when graphics are unavailable.

```sh
herdr plugin install dlv-gold/herdr-md
```

Review and accept Herdr's installation prompt. Herdr downloads the plugin, runs its bootstrap to create a private Python environment, and registers it. Dependencies are downloaded during installation; local viewing then works offline. No separate TeX installation is needed.

For equations and figures, enable graphics in your existing Herdr configuration:

```toml
[terminal]
kitty_graphics = true
```

If `[terminal]` already exists, add or update the setting there. Herdr may need a restart for a configuration change to take effect.

## Open a document

Run this from a shell pane inside Herdr:

```sh
herdr plugin action invoke herdr-md.open
```

A new split opens with a file picker. Choose a Markdown file or enter its path. Edit the document in your usual editor; the preview refreshes after saves. Press `o` to choose another document in the same viewer, or `q` to close the viewer.

Optional shortcut in Herdr's configuration:

```toml
[[keys.command]]
key = "prefix+m"
type = "plugin_action"
command = "herdr-md.open"
description = "open Markdown preview"
```

## Writing documents

Use ordinary Markdown with dollar-delimited math and local PNG references:

```markdown
# Experiment

The energy is $E = mc^2$.

$$
\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}
$$

![Results](figures/results.png)

[More details](details.md)
```

Image paths resolve relative to the Markdown document. Figures scale to fit the pane while preserving their aspect ratio. See [examples/demo.md](examples/demo.md) for a sample with equations, a PNG figure, and document links.

## Controls

| Key | Action |
| --- | --- |
| Arrows / Page Up / Page Down / Home / End | Scroll |
| `/`, then Enter | Search text |
| `n` | Next match |
| `o` | Open another file |
| `r` | Refresh |
| Escape | Close search or cancel the file picker |
| `q` | Quit the viewer |

Prose supports mouse selection. Rendered equations and figures are images, so their contents are not selectable or searchable as text.

## Markdown links

Click a link to another local Markdown document **inside the preview** to open it in a new Herdr pane. When running outside Herdr, the same link loads the document in the current viewer.

The plugin also registers a handler for local Markdown `file://` terminal hyperlinks. When another terminal application emits one, **Ctrl-click** lets Herdr route it to a new preview pane. This requires the terminal to deliver the modified click to Herdr.

The plugin does not make arbitrary plain file paths clickable. On stock Herdr 0.9.0, a printed `/path/to/report.md` needs terminal hyperlink metadata for this handler to run. Links in a separate graphical chat application are handled by that application.

If you install the optional CLI below, you can print a suitable terminal hyperlink yourself:

```sh
herdr-md --print-link /path/to/report.md
```

Ctrl-click its output in a Herdr shell pane. Each activation opens a new split. URL fragments are accepted, but the document opens at its start.

## Standalone CLI (optional)

Installing through Herdr is sufficient for the plugin. It does not add `herdr-md` to your shell's PATH.

For a standalone command, create a local checkout:

```sh
git clone https://github.com/dlv-gold/herdr-md.git
cd herdr-md
python3 scripts/bootstrap.py
mkdir -p ~/.local/bin
ln -s "$PWD/.venv/bin/herdr-md" ~/.local/bin/herdr-md
```

Keep the checkout at this location and ensure `~/.local/bin` is on your PATH. You can also use `.venv/bin/herdr-md` directly.

```sh
herdr-md /path/to/report.md          # view in the current terminal
herdr-md                            # open the file picker
herdr-md --pane /path/to/report.md   # open a new split inside Herdr
```

`--pane` requires the plugin to be installed or linked in Herdr. For a viewer running in the current terminal, use `--no-watch` to disable automatic refresh or `--graphics=text` for text-only rendering:

```sh
herdr-md --no-watch /path/to/report.md
herdr-md --graphics=text /path/to/report.md
```

## Scope and limitations

- This is a local document viewer. It does not edit Markdown or download remote documents and images.
- Math uses Ziamath and latex2mathml and supports common expressions such as fractions, roots, scripts, Greek letters, sums, integrals, and matrices. It is not a full TeX engine with arbitrary packages and macros. Expressions that report rendering errors fall back to LaTeX source.
- Figures must be local PNG files. Other image formats and remote image URLs are unsupported.
- Rendering is a terminal-oriented Markdown subset, not browser or full GitHub Markdown parity. The current viewer uses a dark background.
- Text mode shows LaTeX source and image descriptions instead of graphics. Dollar signs inside code remain literal.

## Uninstall

For an installation managed by Herdr:

```sh
herdr plugin uninstall herdr-md
```

## Development

After creating and bootstrapping a checkout as above, link it for local plugin development:

```sh
herdr plugin link "$PWD"
```

Run checks from the checkout:

```sh
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m build --no-isolation
```

The optional integration test requires Herdr on PATH:

```sh
HERDR_MD_LIVE_TEST=1 .venv/bin/pytest tests/test_live_herdr.py -q
```

It creates a separate plugin registry, configuration, server, and panes; activates a terminal hyperlink twice; and checks that each activation opens another viewer. It stops only its own server. Exercise the demo in Kitty and Herdr after graphics changes, since headless tests do not verify visible rendering.

Unlink a development checkout with `herdr plugin unlink herdr-md`. The checkout remains available.

## License

MIT. See [LICENSE](LICENSE).
