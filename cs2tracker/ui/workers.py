"""Exécution des appels API hors du fil de l'interface.

Toute opération réseau passe par un ``QRunnable`` : l'UI ne se fige jamais,
et chaque erreur est renvoyée sous forme de message déjà lisible.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from cs2tracker.logging_setup import get_logger
from cs2tracker.ui.api_client import ApiError

logger = get_logger(__name__)


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    done = Signal()


class ApiWorker(QRunnable):
    """Exécute un appel bloquant dans le pool de threads Qt."""

    def __init__(self, task: Callable[[], Any]) -> None:
        super().__init__()
        self._task = task
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._task()
        except ApiError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - l'UI doit survivre a tout
            logger.exception("Tache UI en echec")
            self.signals.failed.emit(f"Erreur inattendue: {exc}")
        else:
            self.signals.finished.emit(result)
        finally:
            self.signals.done.emit()


def run_async(
    task: Callable[[], Any],
    on_success: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Lance ``task`` en arrière-plan et branche les callbacks Qt."""
    worker = ApiWorker(task)
    worker.signals.finished.connect(on_success)
    if on_error is not None:
        worker.signals.failed.connect(on_error)
    if on_done is not None:
        worker.signals.done.connect(on_done)
    QThreadPool.globalInstance().start(worker)


class PollingTimer(QObject):
    """Minuteur de rafraîchissement, arrêtable et sans recouvrement d'appels."""

    def __init__(
        self,
        interval_ms: int,
        task: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._task = task
        self._on_success = on_success
        self._on_error = on_error
        self._in_flight = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self._tick()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        # On ne relance jamais une requête tant que la précédente court.
        if self._in_flight:
            return
        self._in_flight = True

        def release() -> None:
            self._in_flight = False

        run_async(self._task, self._on_success, self._on_error, release)
