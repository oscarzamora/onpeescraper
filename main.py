from pathlib import Path
import sys


# Hace visible el paquete bajo src/ cuando se ejecuta el proyecto desde la raíz.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from onpe_scraper.cli import main


# Delega toda la ejecución al CLI del paquete.
if __name__ == "__main__":
    raise SystemExit(main())

