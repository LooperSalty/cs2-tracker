"""Garantit que ``sys.stdout`` et ``sys.stderr`` existent toujours.

Dans une application Windows fenêtrée — donc dans l'exécutable produit avec
``console=False`` — le processus n'a **aucune** console rattachée et Python
laisse `sys.stdout`, `sys.stderr` et `sys.stdin` à ``None``.

La moindre bibliothèque qui suppose leur présence plante alors au démarrage.
Uvicorn le fait dès l'import de son formateur de logs :

    self.use_colors = sys.stdout.isatty()
    AttributeError: 'NoneType' object has no attribute 'isatty'

Ce module doit être importé **avant tout le reste**, y compris avant le paquet
``cs2tracker`` lui-même.
"""

from __future__ import annotations

import io
import sys


class NullStream(io.TextIOBase):
    """Flux texte qui absorbe tout, en exposant l'interface attendue.

    On hérite de ``TextIOBase`` plutôt que de fabriquer un objet factice : les
    bibliothèques testent parfois `isinstance`, `encoding` ou `fileno`.
    """

    encoding = "utf-8"
    errors = "replace"

    def write(self, text: str) -> int:  # noqa: D102 - contrat de TextIOBase
        return len(text)

    def flush(self) -> None:  # noqa: D102
        return None

    def isatty(self) -> bool:  # noqa: D102
        return False

    def readable(self) -> bool:  # noqa: D102
        return False

    def writable(self) -> bool:  # noqa: D102
        return True

    def seekable(self) -> bool:  # noqa: D102
        return False

    def fileno(self) -> int:  # noqa: D102
        # Aucun descripteur reel : lever est le comportement attendu, et les
        # appelants prudents interceptent cette exception.
        raise io.UnsupportedOperation("Aucun descripteur de fichier disponible.")


def ensure_streams() -> None:
    """Remplace les flux standards manquants par des puits silencieux."""
    if sys.stdout is None:
        sys.stdout = NullStream()
    if sys.stderr is None:
        sys.stderr = NullStream()
    if sys.stdin is None:
        sys.stdin = NullStream()
