"""Lanceur de CS2 Tracker.

    python run.py                  fenetre native + API locale (defaut)
    python run.py --browser        interface dans le navigateur
    python run.py --api-only       API seule (http://127.0.0.1:8642/docs)
    python run.py --overlay        lance aussi l'overlay affiche par-dessus CS2
    python run.py --analyse <id>   analyse en console
    python run.py --install-gsi    installe la configuration GSI dans CS2
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permet d'executer le script sans installation prealable du paquet.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# DOIT precede tout autre import : l'executable est fenetre, donc depourvu de
# console, et Python laisse alors sys.stdout a None. Uvicorn plante des son
# import s'il n'est pas remis en place.
from cs2tracker.std_streams import ensure_streams  # noqa: E402

ensure_streams()

from cs2tracker.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
