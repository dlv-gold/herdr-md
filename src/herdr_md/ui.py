"""Selectable terminal document with an independently clipped graphics plane."""

import asyncio
import difflib
import os
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rich.segment import Segment
from textual import events
from textual.app import App, ComposeResult
from textual.geometry import Size
from textual.screen import ModalScreen
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import DirectoryTree, Footer, Header, Input, Static
from watchfiles import awatch

from .document import Document, build
from .graphics import Graphics
from .herdr import checked_file, local_file, open_pane


class MarkdownTree(DirectoryTree):
    def filter_paths(self, paths):
        return [
            p
            for p in paths
            if not p.name.startswith(".")
            and (p.is_dir() or p.suffix.lower() in {".md", ".markdown"})
        ]


class FilePicker(ModalScreen[Path | None]):
    DEFAULT_CSS = """
    FilePicker { background: $background; padding: 1 2; }
    FilePicker Input { dock: top; }
    FilePicker Static { height: 2; dock: bottom; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory

    def compose(self):
        yield Input(
            value=str(self.directory) + "/", placeholder="Markdown file path", id="filename"
        )
        yield MarkdownTree(self.directory)
        yield Static(
            "Choose a Markdown file, or enter its path. Escape cancels.", id="picker-status"
        )

    def choose(self, value):
        try:
            path = Path(value).expanduser()
            self.dismiss(checked_file(path if path.is_absolute() else self.directory / path))
        except (OSError, ValueError) as exc:
            self.query_one("#picker-status", Static).update(str(exc))

    def on_input_submitted(self, event: Input.Submitted):
        self.choose(event.value)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        self.choose(event.path)

    def action_cancel(self):
        self.dismiss(None)


class DocumentView(ScrollView):
    can_focus = True
    ALLOW_SELECT = True
    DEFAULT_CSS = "DocumentView { height: 1fr; scrollbar-gutter: stable; background: #181825; color: #e6e6e6; }"

    def __init__(self):
        super().__init__(id="document")
        self.document = Document()
        self.search_query = ""
        self.selected = None

    def replace(self, document: Document):
        old = self.document
        position = min(int(self.scroll_y), max(0, len(old.lines) - 1))
        source_row = old.source_rows[position] if old.source_rows else 0
        first = old.source_rows.index(source_row) if old.source_rows else 0
        offset = position - first
        # Map an unchanged source block across insertions/deletions above the viewport.
        if old.source_lines != document.source_lines:
            for match in difflib.SequenceMatcher(
                a=old.source_lines, b=document.source_lines
            ).get_matching_blocks():
                if match.a <= source_row < match.a + match.size:
                    source_row = match.b + source_row - match.a
                    break
        self.document = document
        self.virtual_size = Size(self.scrollable_content_region.width, len(document.lines))
        closest = (
            min(
                range(len(document.source_rows)),
                key=lambda i: abs(document.source_rows[i] - source_row),
            )
            if document.source_rows
            else 0
        )
        self.scroll_to(y=closest + offset, animate=False, force=True, immediate=True)
        self.refresh()

    def render_line(self, y):
        row = y + int(self.scroll_y)
        width = self.scrollable_content_region.width
        if row >= len(self.document.lines):
            return Strip.blank(width, self.rich_style)
        line = self.document.lines[row].copy()
        if self.search_query:
            line.highlight_words([self.search_query], style="black on yellow", case_sensitive=False)
        if self.selected and (span := self.selected.get_span(row)):
            line.stylize("on #45475a", span[0], None if span[1] == -1 else span[1])
        return (
            Strip(
                list(Segment.apply_style(line.render(self.app.console), self.rich_style))
                or [Segment("", self.rich_style)]
            )
            .extend_cell_length(width, self.rich_style)
            .crop(0, width)
            .apply_offsets(0, row)
        )

    def get_selection(self, selection):
        lines = []
        for row, line in enumerate(self.document.lines):
            if (span := selection.get_span(row)) is not None:
                start, end = span
                # Textual selection offsets index characters, not terminal cells.
                lines.append(line.plain[start : None if end < 0 else end])
        return "\n".join(lines), "\n"

    def selection_updated(self, selection):
        self.selected = selection
        self.refresh()

    def on_click(self, event: events.Click):
        row = event.y + int(self.scroll_y)
        for y, start, end, href in self.document.links:
            if row == y and start <= event.x < end:
                self.app.follow_link(href)
                break


class Viewer(App):
    TITLE = "Markdown Preview"
    CSS = """
    Screen { background: #181825; }
    #status { height: 1; color: #a6adc8; background: #181825; }
    #search { dock: bottom; height: 3; display: none; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("o", "open", "Open"),
        ("r", "reload", "Refresh"),
        ("slash", "search", "Search"),
        ("n", "next_match", "Next match"),
        ("escape", "close_search", "Close search"),
    ]

    def __init__(self, path=None, watch=True, graphics="auto", backend=None):
        super().__init__()
        self.path = path
        self.watch_enabled = watch
        self.backend = backend or Graphics(graphics)
        self.generation = 0
        self.epoch = 0
        self.last_frame = None
        self.last_width = 0
        self.watcher = None
        self.render_task = None
        self.paint_lock = asyncio.Lock()
        self.load_lock = asyncio.Lock()
        self.last_metrics_check = 0.0
        self.dependencies = set()
        self.view = DocumentView()
        self.directory = (
            path.parent if path else Path(os.environ.get("HERDR_MD_DIRECTORY", os.getcwd()))
        )

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.view
        yield Static("", id="status")
        yield Input(placeholder="Search text (Enter finds next)", id="search")
        yield Footer()

    async def on_mount(self):
        self.view.focus()
        self.set_interval(0.1, self.tick)
        if self.path:
            self.call_after_refresh(self.request_reload)
        else:
            await self.action_open()

    def write_graphics(self, data):
        if self._driver:
            self._driver.write(data)

    def status(self, text):
        self.query_one("#status", Static).update(text)

    def request_reload(self):
        self.generation += 1
        if self.path:
            generation = self.generation
            self.render_task = asyncio.create_task(self.reload_document(generation, self.path))

    async def reload_document(self, generation, path):
        width = max(8, self.view.scrollable_content_region.width)
        try:
            async with self.load_lock:
                if generation != self.generation:
                    return
                source = await asyncio.to_thread(path.read_text, encoding="utf-8")
                document = await asyncio.to_thread(
                    build, source, path, width, self.backend.cell, self.backend.mode != "text"
                )
        except (OSError, ValueError) as exc:
            if generation == self.generation:
                self.status(f"{exc} — keeping the last readable preview")
            return
        if generation != self.generation:
            return
        self.last_width = width
        self.view.replace(document)
        self.epoch += 1
        self.title = path.name
        detail = f"{path} · {self.backend.mode} · {'live' if self.watch_enabled else 'manual'}"
        if document.errors:
            detail += " · " + document.errors[0]
        self.status(detail)
        dependencies = {path, *document.dependencies}
        if self.watch_enabled and dependencies != self.dependencies:
            self.dependencies = dependencies
            if self.watcher:
                self.watcher.cancel()
            self.watcher = asyncio.create_task(self.watch_paths(dependencies))

    async def watch_paths(self, dependencies):
        # Watching parents also catches editor rename-and-replace saves.
        parents = {p.parent for p in dependencies}
        # Missing nested image directories are watched from their nearest existing ancestor.
        roots = set()
        for parent in parents:
            while not parent.is_dir() and parent != parent.parent:
                parent = parent.parent
            roots.add(parent)
        try:
            async for changes in awatch(*roots, debounce=200, step=50, watch_filter=None):
                if any(Path(p).resolve() in dependencies for _, p in changes):
                    self.request_reload()
        except asyncio.CancelledError:
            pass
        except OSError as exc:
            self.status(f"Live refresh unavailable: {exc}; use r to refresh")

    async def tick(self):
        if not self.view.is_attached or self.paint_lock.locked():
            return
        if self.screen is not self.view.screen:
            if self.last_frame is not None:
                async with self.paint_lock:
                    self.backend.clear(self.write_graphics)
                self.last_frame = None
            return
        region = self.view.scrollable_content_region
        changed_metrics = False
        if time.monotonic() - self.last_metrics_check >= 1:
            self.last_metrics_check = time.monotonic()
            old_cell = self.backend.cell
            try:
                await asyncio.to_thread(self.backend.measure)
            except (OSError, ValueError):
                pass
            changed_metrics = old_cell != self.backend.cell
        if self.path and (region.width != self.last_width or changed_metrics):
            self.last_width = region.width
            self.request_reload()
        key = (self.epoch, int(self.view.scroll_y), region)
        if key == self.last_frame or not self.view.document.lines:
            return
        self.last_frame = key
        async with self.paint_lock:
            try:
                frame = self.view.document.frame(
                    region.width, region.height, int(self.view.scroll_y), self.backend.cell
                )
                await asyncio.to_thread(
                    self.backend.present,
                    frame,
                    region.x,
                    region.y,
                    region.width,
                    region.height,
                    self.write_graphics,
                )
            except (OSError, ValueError) as exc:
                self.backend.clear(self.write_graphics)
                self.backend.mode = "text"
                self.status(f"Graphics unavailable: {exc}; switching to text")
                self.request_reload()

    async def action_open(self):
        async with self.paint_lock:
            self.backend.clear(self.write_graphics)
        self.push_screen(FilePicker(self.directory), self.picked)

    def picked(self, path):
        self.last_frame = None
        if path:
            self.path, self.directory = path, path.parent
            self.view.document = Document()
            self.view.scroll_to(y=0, animate=False)
            self.request_reload()
        self.view.focus()

    def action_reload(self):
        self.request_reload()

    def action_search(self):
        search = self.query_one("#search", Input)
        search.display = True
        search.focus()

    def action_close_search(self):
        self.query_one("#search", Input).display = False
        self.view.focus()

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search":
            self.view.search_query = event.value
            self.view.refresh()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search":
            self.action_next_match()
            self.action_close_search()

    def action_next_match(self):
        query = self.view.search_query.casefold()
        if not query:
            return
        lines = self.view.document.lines
        start = int(self.view.scroll_y) + 1
        for i in [*range(start, len(lines)), *range(min(start, len(lines)))]:
            if query in lines[i].plain.casefold():
                self.view.scroll_to(y=i, animate=False, immediate=True)
                return
        self.status(f"No matches for {self.view.search_query!r}")

    def follow_link(self, href):
        parsed = urlsplit(href)
        try:
            if parsed.scheme == "file":
                path = local_file(href)
            elif parsed.scheme in {"http", "https"}:
                self.open_url(href)
                return
            elif not parsed.scheme and parsed.path:
                path = checked_file(self.directory / unquote(parsed.path))
            else:
                self.status("Use the terminal link opener for web links")
                return
            if os.environ.get("HERDR_ENV") == "1":
                open_pane(path)
            else:
                self.picked(path)
        except (OSError, ValueError) as exc:
            self.status(str(exc))

    async def on_unmount(self):
        self.generation += 1
        if self.watcher:
            self.watcher.cancel()
        if self.render_task:
            self.render_task.cancel()
        async with self.paint_lock:
            self.backend.clear(self.write_graphics)
