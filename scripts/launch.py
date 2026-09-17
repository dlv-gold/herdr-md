import os
import sys
from pathlib import Path

python = Path(__file__).resolve().parents[1] / ".venv/bin/python"
if not python.exists():
    raise SystemExit("Run python3 scripts/bootstrap.py before linking herdr-md")
os.execv(str(python), [str(python), "-m", "herdr_md", *sys.argv[1:]])
