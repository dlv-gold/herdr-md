import asyncio

import pytest
from PIL import Image
from textual.geometry import Offset
from textual.selection import Selection

from herdr_md.ui import FilePicker, Viewer


async def eventually(predicate, timeout=4):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.05)


async def test_open_search_resize_and_picker(tmp_path):
    file = tmp_path / "test.md"
    file.write_text("# Heading\n\n" + "\n\n".join(f"Paragraph {i}" for i in range(60)))
    app = Viewer(file, watch=False, graphics="text")
    async with app.run_test(size=(80, 24)) as pilot:
        await eventually(lambda: len(app.view.document.lines) > 50)
        # Let Textual apply the loaded document size before simulating user input.
        await pilot.pause()
        app.view.search_query = "Paragraph 20"
        app.action_next_match()
        await pilot.pause()
        assert app.view.scroll_y > 0
        await pilot.resize_terminal(40, 20)
        await eventually(lambda: app.last_width < 40)
        await pilot.press("o")
        assert isinstance(app.screen, FilePicker)
        await pilot.press("escape")
        assert not isinstance(app.screen, FilePicker)


async def test_initial_picker():
    app = Viewer(watch=False, graphics="text")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FilePicker)


async def test_selection_uses_textual_character_offsets(tmp_path):
    path = tmp_path / "unicode.md"
    path.write_text("界界abcdef")
    app = Viewer(path, watch=False, graphics="text")
    async with app.run_test():
        await eventually(lambda: bool(app.view.document.lines))
        text, _ = app.view.get_selection(Selection(Offset(2, 0), Offset(5, 0)))
        assert text == "abc"


async def test_refresh_keeps_reading_block_after_insertion(tmp_path):
    path = tmp_path / "reading.md"
    source = "\n\n".join(f"Paragraph {i}" for i in range(80))
    path.write_text(source)
    app = Viewer(path, watch=False, graphics="text")
    async with app.run_test() as pilot:
        await eventually(lambda: bool(app.view.document.lines))
        await pilot.pause(0.2)
        app.view.search_query = "Paragraph 30"
        app.action_next_match()
        old_epoch = app.epoch
        path.write_text("# New section\n\nInserted above the reader.\n\n" + source)
        app.request_reload()
        await eventually(lambda: app.epoch > old_epoch)
        assert "Paragraph 30" in app.view.document.lines[int(app.view.scroll_y)].plain


async def test_live_save_delete_recreate_and_image_replacement(tmp_path):
    file = tmp_path / "test.md"
    file.write_text("First\n\n![](p.png)")
    image = tmp_path / "p.png"
    Image.new("RGB", (10, 10), "red").save(image)
    app = Viewer(file, graphics="text")
    async with app.run_test() as pilot:
        await eventually(lambda: file in app.dependencies)
        await pilot.pause(0.3)
        replacement = tmp_path / "new.md"
        replacement.write_text("Second\n\n![](p.png)")
        replacement.replace(file)
        await eventually(lambda: any("Second" in line.plain for line in app.view.document.lines))
        epoch = app.epoch
        Image.new("RGB", (10, 10), "blue").save(image)
        await eventually(lambda: app.epoch > epoch)
        file.unlink()
        await pilot.pause(0.3)
        assert any("Second" in line.plain for line in app.view.document.lines)
        file.write_text("Third")
        await eventually(lambda: any("Third" in line.plain for line in app.view.document.lines))


async def test_stale_document_cannot_replace_new_file(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("Old")
    b = tmp_path / "b.md"
    b.write_text("New")
    app = Viewer(a, watch=False, graphics="text")
    async with app.run_test():
        await eventually(lambda: bool(app.view.document.lines))
        old_generation = app.generation
        app.picked(b)
        await app.reload_document(old_generation, a)
        await eventually(lambda: any("New" in line.plain for line in app.view.document.lines))
        assert not any("Old" in line.plain for line in app.view.document.lines)


@pytest.mark.parametrize(
    ("source", "start", "end", "expected"),
    [
        ("alpha beta gamma", (6, 0), (9, 0), "beta"),
        ("alpha beta gamma", (9, 0), (6, 0), "beta"),
        ("界界abcdef", (4, 0), (6, 0), "abc"),
        ("first line\n\nsecond line", (6, 0), (5, 2), "line\n\nsecond"),
    ],
)
async def test_mouse_drag_selects_only_dragged_text(tmp_path, source, start, end, expected):
    path = tmp_path / "selection.md"
    path.write_text(source)
    app = Viewer(path, watch=False, graphics="text")
    async with app.run_test() as pilot:
        await eventually(lambda: bool(app.view.document.lines))
        await pilot.pause()
        await pilot.mouse_down("#document", offset=start)
        await pilot.hover("#document", offset=end)
        await pilot.mouse_up("#document", offset=end)
        await pilot.pause()
        assert app.screen.get_selected_text() == expected
        assert app.view.selected.start is not None
        assert app.view.selected.end is not None
        # Selection must not paint unrelated text at the start of the document.
        assert next(iter(app.view.render_line(0))).style.bgcolor.triplet != (69, 71, 90)


async def test_mouse_selection_after_scrolling(tmp_path):
    path = tmp_path / "scroll.md"
    path.write_text("\n\n".join(f"row {i:02d} content" for i in range(50)))
    app = Viewer(path, watch=False, graphics="text")
    async with app.run_test(size=(80, 20)) as pilot:
        await eventually(lambda: len(app.view.document.lines) > 50)
        await pilot.pause()
        app.view.scroll_to(y=20, animate=False, immediate=True)
        await pilot.pause()
        await pilot.mouse_down("#document", offset=(0, 0))
        await pilot.hover("#document", offset=(5, 0))
        await pilot.mouse_up("#document", offset=(5, 0))
        assert app.screen.get_selected_text() == "row 10"


async def test_png_link_opens_new_herdr_preview(tmp_path, monkeypatch):
    path = tmp_path / "report.md"
    image = tmp_path / "figure #1.png"
    Image.new("RGB", (16, 12), "red").save(image)
    path.write_text("[Figure](figure%20%231.png)")
    opened = []
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setattr("herdr_md.ui.open_pane", lambda target: opened.append(target))
    app = Viewer(path, watch=False, graphics="text")
    async with app.run_test() as pilot:
        await eventually(lambda: bool(app.view.document.lines))
        await pilot.pause()
        await pilot.click("#document", offset=(2, 0))
        assert opened == [image]


async def test_png_opens_as_image_and_refreshes(tmp_path):
    from herdr_md.graphics import Graphics

    path = tmp_path / "figure #1.png"
    Image.new("RGB", (16, 12), "red").save(path)
    backend = Graphics("text")
    backend.mode = "kitty"
    backend.measure = lambda: backend.cell
    backend.present = lambda *args: None
    app = Viewer(path, backend=backend)
    async with app.run_test() as pilot:
        await eventually(lambda: bool(app.view.document.pictures))
        assert not app.view.document.errors
        assert app.view.document.pictures[0].image.getpixel((0, 0))[:3] == (255, 0, 0)
        await eventually(lambda: path in app.dependencies)
        await pilot.pause(0.3)
        Image.new("RGB", (16, 12), "blue").save(path)
        await eventually(
            lambda: app.view.document.pictures[0].image.getpixel((0, 0))[:3] == (0, 0, 255)
        )
