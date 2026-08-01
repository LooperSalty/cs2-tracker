"""Lanceur de CS2 Tracker.

    python run.py                  interface web + API locale (defaut)
    python run.py --desktop        fenetre native Qt
    python run.py --api-only       API seule (http://127.0.0.1:8642/docs)
    python run.py --analyse <id>   analyse en console
    python run.py --install-gsi    installe la configuration GSI dans CS2
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permet d'exécuter le script sans installation préalable du paquet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cs2tracker.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
