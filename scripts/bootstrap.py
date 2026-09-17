"""Install exactly the locked dependencies into a checkout-local environment."""

import subprocess
import sys
import venv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if sys.version_info < (3, 12):  # noqa: UP036 - standalone bootstrap precedes installation
    raise SystemExit("Herdr MD requires Python 3.12 or newer")
python = root / ".venv/bin/python"
if not python.exists():
    venv.EnvBuilder(with_pip=True).create(root / ".venv")
subprocess.run(
    [str(python), "-m", "pip", "install", "-r", str(root / "requirements.lock")], check=True
)
subprocess.run(
    [str(python), "-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", str(root)],
    check=True,
)
