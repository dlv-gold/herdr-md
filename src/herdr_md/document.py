"""Parse and measure a document into terminal rows and pixel placements."""

import io
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

import resvg_py
import ziamath
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from PIL import Image
from rich.cells import cell_len
from rich.style import Style
from rich.text import Text


@dataclass
class Picture:
    image: Image.Image
    x: int
    y: int
    dy: int = 0


@dataclass
class Document:
    lines: list[Text] = field(default_factory=list)
    source_rows: list[int] = field(default_factory=list)
    source_lines: list[str] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    links: list[tuple[int, int, int, str]] = field(default_factory=list)
    dependencies: set[Path] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    def frame(self, width: int, height: int, scroll: int, cell: tuple[int, int]) -> Image.Image:
        cw, ch = cell
        frame = Image.new("RGBA", (max(1, width * cw), max(1, height * ch)))
        for picture in self.pictures:
            y = (picture.y - scroll) * ch + picture.dy
            if y < frame.height and y + picture.image.height > 0:
                frame.alpha_composite(picture.image, (picture.x * cw, y))
        return frame


@lru_cache(maxsize=128)
def equation(source: str, size: int, color: str, inline=False) -> Image.Image:
    svg = ziamath.Latex(source, size=size, color=color, inline=inline).svg()
    image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA")
    image.info["baseline"] = -float(ET.fromstring(svg).attrib["viewBox"].split()[1])
    return image


class Layout:
    def __init__(self, width: int, cell: tuple[int, int], graphics: bool):
        self.width = max(8, width)
        self.cw, self.ch = cell
        self.graphics = graphics
        self.doc = Document()
        self.line = Text()
        self.pending: list[tuple[Image.Image, int]] = []
        self.line_links: list[tuple[int, int, str]] = []
        self.row = 0

    def flush(self):
        text_baseline = round(self.ch * 0.8)
        ascent = max([text_baseline, *(p.info.get("baseline", p.height) for p, _ in self.pending)])
        text_row = max(0, math.ceil((ascent - text_baseline) / self.ch))
        baseline = text_row * self.ch + text_baseline
        image_offsets = [
            max(0, round(baseline - p.info.get("baseline", p.height))) for p, _ in self.pending
        ]
        height = max(
            [
                text_row + 1,
                *(
                    math.ceil((dy + p.height) / self.ch)
                    for (p, _), dy in zip(self.pending, image_offsets)
                ),
            ]
        )
        y = len(self.doc.lines)
        rows = [Text() for _ in range(height)]
        rows[text_row] = self.line
        self.doc.lines.extend(rows)
        self.doc.source_rows.extend([self.row] * height)
        for (image, x), dy in zip(self.pending, image_offsets):
            self.doc.pictures.append(Picture(image, x, y, dy))
        self.doc.links.extend((y + text_row, a, b, url) for a, b, url in self.line_links)
        self.line, self.pending, self.line_links = Text(), [], []

    def text(self, value: str, style="", link: str | None = None, wrap_words=True):
        if wrap_words:
            for word in re.findall(r"\n|[^\S\n]+|[^\s]+", value):
                length = cell_len(word)
                if (
                    not word.isspace()
                    and length <= self.width
                    and self.line.cell_len + length > self.width
                ):
                    self.flush()
                self.text(word, style, link, wrap_words=False)
            return
        # Rich measures wide Unicode characters in terminal cells.
        for char in value:
            if char == "\n":
                self.flush()
                continue
            if self.line.cell_len + cell_len(char) > self.width:
                self.flush()
            start = self.line.cell_len
            self.line.append(char if char.isprintable() or char == "\t" else "", style=style)
            if link:
                self.line_links.append((start, self.line.cell_len, link))

    def image(self, image: Image.Image, block=False):
        if block and (self.line or self.pending):
            self.flush()
        max_width = self.width * self.cw
        if image.width > max_width:
            baseline = image.info.get("baseline")
            scale = max_width / image.width
            image = image.resize(
                (max_width, max(1, round(image.height * max_width / image.width))),
                Image.Resampling.LANCZOS,
            )
            if baseline is not None:
                image.info["baseline"] = baseline * scale
        if block:
            height = math.ceil(image.height / self.ch)
            self.doc.pictures.append(Picture(image, 0, len(self.doc.lines)))
            self.doc.lines.extend(Text() for _ in range(height))
            self.doc.source_rows.extend([self.row] * height)
            return
        cells = math.ceil(image.width / self.cw)
        if self.line.cell_len + cells > self.width:
            self.flush()
        self.pending.append((image, self.line.cell_len))
        self.line.append(" " * cells)


def image_path(src: str, directory: Path) -> Path:
    parsed = urlsplit(src)
    if parsed.scheme or parsed.netloc:
        raise ValueError("Only local PNG references are supported")
    path = (directory / unquote(parsed.path)).resolve()
    if path.suffix.lower() != ".png":
        raise ValueError("Only PNG figures are supported")
    return path


def build(
    source: str, path: Path, width: int, cell=(8, 16), graphics=True, color="#e6e6e6"
) -> Document:
    layout = Layout(width, cell, graphics)
    layout.doc.source_lines = source.splitlines()
    parser = MarkdownIt("commonmark").enable(["table", "strikethrough"]).use(dollarmath_plugin)
    indent = 0
    heading = False
    style_stack = []

    def math_token(value: str, block=False):
        if graphics:
            try:
                layout.image(
                    equation(value, max(14, round(cell[1] * 1.1)), color, inline=not block), block
                )
                return
            except Exception as exc:
                layout.doc.errors.append(f"Math: {exc}")
        layout.text(("$$" if block else "$") + value + ("$$" if block else "$"), "cyan")
        if block:
            layout.flush()

    def inline(tokens):
        link = None
        for token in tokens:
            kind = token.type
            if kind in {"strong_open", "em_open", "s_open"}:
                style_stack.append(
                    {"strong_open": "bold", "em_open": "italic", "s_open": "strike"}[kind]
                )
            elif kind in {"strong_close", "em_close", "s_close"}:
                if style_stack:
                    style_stack.pop()
            elif kind == "link_open":
                link = token.attrGet("href")
            elif kind == "link_close":
                link = None
            elif kind == "math_inline":
                math_token(token.content)
            elif kind == "image":
                try:
                    figure = image_path(token.attrGet("src") or "", path.parent)
                    layout.doc.dependencies.add(figure)
                    if graphics:
                        with Image.open(figure) as img:
                            if img.format != "PNG":
                                raise ValueError("Image is not a PNG")
                            img.thumbnail((layout.width * cell[0], 4096))
                            layout.image(img.convert("RGBA"), block=True)
                    else:
                        layout.text(f"[PNG: {token.content or figure.name}]", "dim")
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    layout.doc.errors.append(str(exc))
                    layout.text(
                        f"[Image: {token.content or token.attrGet('src')} — {exc}]", "yellow"
                    )
            elif kind in {"softbreak", "hardbreak"}:
                layout.text(" " if kind == "softbreak" else "\n")
            elif kind in {"text", "code_inline", "html_inline"}:
                style = " ".join(
                    style_stack
                    + (["bold cyan"] if heading else [])
                    + (["reverse"] if kind == "code_inline" else [])
                    + (["underline cyan"] if link else [])
                )
                layout.text(token.content, Style.parse(style) if style else "", link)

    for token in parser.parse(source):
        if token.map:
            layout.row = token.map[0]
        kind = token.type
        if kind == "heading_open":
            heading = True
        elif kind == "heading_close":
            layout.flush()
            layout.flush()
            heading = False
        elif kind in {"bullet_list_open", "ordered_list_open", "blockquote_open"}:
            indent += 1
        elif kind in {"bullet_list_close", "ordered_list_close", "blockquote_close"}:
            indent = max(0, indent - 1)
        elif kind == "list_item_open":
            layout.text("  " * max(0, indent - 1) + "• ")
        elif kind == "inline":
            inline(token.children or [])
        elif kind == "paragraph_close":
            if layout.line or layout.pending:
                layout.flush()
            layout.flush()
        elif kind in {"math_block", "math_block_label"}:
            math_token(token.content, True)
            layout.flush()
        elif kind in {"fence", "code_block"}:
            for offset, line in enumerate(token.content.splitlines()):
                layout.row = (token.map[0] if token.map else 0) + offset
                layout.text(line.expandtabs(4), "green", wrap_words=False)
                layout.flush()
            layout.flush()
        elif kind == "hr":
            layout.text("─" * layout.width, "dim")
            layout.flush()
        elif kind in {"th_close", "td_close"}:
            layout.text(" │ ", "dim")
        elif kind == "tr_close":
            layout.flush()
    if layout.line or layout.pending:
        layout.flush()
    return layout.doc
