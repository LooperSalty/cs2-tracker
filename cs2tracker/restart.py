"""Redémarrage propre de l'application.

Certains réglages — la clé API Steam en premier lieu — ne sont lus qu'au
démarrage : le client Steam est construit une fois, à l'ouverture. Plutôt que
de demander à l'utilisateur de fermer puis rouvrir, l'application se relance
elle-même.

Le point délicat est le port : la nouvelle instance ne peut pas s'y attacher
tant que l'ancienne le détient. Elle est donc lancée avec ``--wait-for-pid``,
et patiente jusqu'à la disparition du processus qui l'a engendrée.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Permet au nouveau processus de sortir du Job Object de son parent. Absent de
#: ``subprocess`` : la constante vient directement de l'API Win32.
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000

#: Délai laissé à la réponse HTTP pour partir avant que le processus ne meure.
_GRACE_SECONDS = 0.7
#: Au-delà, on considère que l'ancien processus ne rendra jamais la main.
_MAX_WAIT_SECONDS = 20.0
_POLL_INTERVAL = 0.2


def _relaunch_command() -> list[str]:
    """Reconstruit la ligne de commande de l'instance courante."""
    if getattr(sys, "frozen", False):
        # Executable PyInstaller : sys.executable est l'application elle-meme.
        command = [sys.executable]
    else:
        command = [sys.executable, os.path.abspath(sys.argv[0])]

    # On repasse les arguments d'origine, sans un eventuel --wait-for-pid
    # herite d'un redemarrage precedent.
    arguments = list(sys.argv[1:])
    if "--wait-for-pid" in arguments:
        index = arguments.index("--wait-for-pid")
        del arguments[index : index + 2]

    return command + arguments + ["--wait-for-pid", str(os.getpid())]


def _stable_working_directory() -> str:
    """Répertoire qui survivra à la fin du processus courant."""
    if getattr(sys, "frozen", False):
        return str(os.path.dirname(os.path.abspath(sys.executable)))
    return os.getcwd()


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_for_process(pid: int, timeout: float = _MAX_WAIT_SECONDS) -> bool:
    """Attend la fin du processus ``pid``. Renvoie False en cas d'expiration."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_is_alive(pid):
            # Court repit : Windows libere le port peu apres la fin du processus.
            time.sleep(0.3)
            return True
        time.sleep(_POLL_INTERVAL)
    logger.warning("Le processus %s ne s'est pas termine dans le delai imparti.", pid)
    return False


def schedule_restart(on_shutdown: "callable[[], None] | None" = None) -> bool:
    """Lance une nouvelle instance puis arrête celle-ci.

    ``on_shutdown`` permet à l'appelant de fermer proprement ses ressources
    (fenêtre, icône système) avant la sortie.
    """
    command = _relaunch_command()
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        # CREATE_BREAKAWAY_FROM_JOB est indispensable : le lanceur PyInstaller
        # place son processus applicatif dans un Job Object, et la destruction
        # de ce job emporte tous ses membres. Sans ce drapeau, la nouvelle
        # instance est tuee quelques instants apres sa naissance, au moment ou
        # l'ancienne se termine.
        creation_flags |= _CREATE_BREAKAWAY_FROM_JOB

    # Le repertoire courant peut etre le dossier temporaire d'extraction de
    # PyInstaller, efface des la fin du processus. On se replace donc dans le
    # dossier de l'executable, qui lui subsiste.
    working_directory = _stable_working_directory()

    try:
        subprocess.Popen(
            command,
            cwd=working_directory,
            creationflags=creation_flags,
            close_fds=True,
        )
    except OSError as exc:
        # Tous les jobs n'autorisent pas l'evasion. On retente sans le drapeau
        # plutot que d'abandonner le redemarrage.
        logger.warning("Lancement avec breakaway refuse (%s), nouvel essai.", exc)
        try:
            subprocess.Popen(
                command,
                cwd=working_directory,
                creationflags=creation_flags & ~_CREATE_BREAKAWAY_FROM_JOB,
                close_fds=True,
            )
        except OSError:
            logger.exception("Redemarrage impossible.")
            return False

    logger.info("Nouvelle instance lancee, arret de celle-ci.")

    def terminate() -> None:
        # Laisse la reponse HTTP atteindre le client avant de couper.
        time.sleep(_GRACE_SECONDS)
        if on_shutdown is not None:
            try:
                on_shutdown()
            except Exception as exc:  # noqa: BLE001 - l'arret prime sur tout
                logger.debug("Nettoyage avant redemarrage : %s", exc)
        # `os._exit` court-circuite les gestionnaires atexit : la nouvelle
        # instance attend la liberation du port, il faut la lui rendre vite.
        os._exit(0)

    threading.Thread(target=terminate, name="cs2tracker-restart", daemon=True).start()
    return True


#: Rappel enregistré par l'application de bureau pour fermer sa fenêtre.
_shutdown_hook: "callable[[], None] | None" = None


def set_shutdown_hook(hook: "callable[[], None] | None") -> None:
    global _shutdown_hook
    _shutdown_hook = hook


def restart_now() -> bool:
    return schedule_restart(_shutdown_hook)
