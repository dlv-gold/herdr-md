import argparse
import json
import os
import sys
from pathlib import Path

from .herdr import checked_file, local_file, open_pane, report_error


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Live Markdown, LaTeX and PNG previews")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--pane", action="store_true", help="Open a new Herdr split")
    parser.add_argument(
        "--print-link", action="store_true", help="Print a Ctrl-clickable file hyperlink"
    )
    parser.add_argument("--no-watch", action="store_true")
    parser.add_argument("--graphics", choices=["auto", "text"], default="auto")
    parser.add_argument("--action", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        context = (
            json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}")) if args.action else {}
        )
        clicked = (
            context.get("clicked_url") or os.environ.get("HERDR_PLUGIN_CLICKED_URL", "")
            if args.action
            else ""
        )
        filename = args.file or (os.environ.get("HERDR_MD_FILE") if not args.action else None)
        path = (
            local_file(clicked) if clicked else checked_file(Path(filename)) if filename else None
        )
        if args.print_link:
            if path is None:
                parser.error("--print-link requires a file")
            label = "".join(c for c in str(path) if c.isprintable())
            print(f"\x1b]8;;{path.as_uri()}\x1b\\{label}\x1b]8;;\x1b\\")
        elif args.action or args.pane:
            open_pane(path, context)
        else:
            from .ui import Viewer

            Viewer(path, watch=not args.no_watch, graphics=args.graphics).run()
        return 0
    except (OSError, ValueError) as exc:
        print(f"herdr-md: {exc}", file=sys.stderr)
        if args.action:
            report_error(str(exc))
        return 1
