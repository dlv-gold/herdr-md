from pathlib import Path

import pytest
from PIL import Image

from herdr_md.document import build, equation


@pytest.mark.parametrize(
    "math",
    [
        r"\frac{a}{b}",
        r"\sqrt{x^2 + y^2}",
        r"\sum_{n=0}^{\infty}x^n",
        r"\int_0^1 f(x) dx",
        r"\begin{pmatrix}a&b\\c&d\end{pmatrix}",
    ],
)
def test_math_pixels(math):
    image = equation(math, 24, "#ffffff")
    assert image.width > 0 and image.height > 0
    assert image.getbbox()


def test_code_and_escaped_dollars_are_not_math():
    doc = build('`$x$` and \\$5\n\n```python\nx = "$y$"\n```\n\nreal $z$', Path("x.md"), 80)
    assert len(doc.pictures) == 1
    assert "$x$" in "\n".join(x.plain for x in doc.lines)


def test_many_math_images_share_one_clipped_frame():
    doc = build(" ".join("$x$" for _ in range(30)), Path("x.md"), 20)
    assert len(doc.pictures) == 30
    frame = doc.frame(20, 3, 1, (8, 16))
    assert frame.size == (160, 48)
    assert frame.getbbox()
    assert all(line.cell_len <= 20 for line in doc.lines)


def test_relative_png_with_spaces(tmp_path):
    figure = tmp_path / "figure one.png"
    Image.new("RGB", (1000, 500), "red").save(figure)
    doc = build("![Figure](figure%20one.png)", tmp_path / "x.md", 20)
    assert figure in doc.dependencies
    assert doc.pictures[0].image.size == (160, 80)
    assert not doc.errors


def test_missing_image_remains_watched(tmp_path):
    doc = build("![Missing](missing.png)", tmp_path / "x.md", 80)
    assert tmp_path / "missing.png" in doc.dependencies
    assert doc.errors
    assert "Missing" in "\n".join(line.plain for line in doc.lines)


def test_corrupt_image_and_text_fallback(tmp_path):
    (tmp_path / "broken.png").write_text("not PNG")
    doc = build("![Oops](broken.png)", tmp_path / "x.md", 80)
    assert doc.errors and not doc.pictures
    doc = build(
        "Inline $x^2$\n\n$$x+y$$\n\n![plot](broken.png)", tmp_path / "x.md", 80, graphics=False
    )
    text = "\n".join(line.plain for line in doc.lines)
    assert "$x^2$" in text and "$$x+y$$" in text and "[PNG: plot]" in text


def test_unicode_links_and_wrapping():
    doc = build("[界界abcdef](other.md)", Path("x.md"), 8, graphics=False)
    assert all(line.cell_len <= 8 for line in doc.lines)
    assert all(link[3] == "other.md" for link in doc.links)


def test_png_replacement_changes_render(tmp_path):
    file = tmp_path / "p.png"
    Image.new("RGB", (8, 16), "red").save(file)
    first = build("![](p.png)", tmp_path / "a.md", 80)
    Image.new("RGB", (8, 16), "blue").save(file)
    second = build("![](p.png)", tmp_path / "a.md", 80)
    assert first.pictures[0].image.getpixel((0, 0)) != second.pictures[0].image.getpixel((0, 0))
