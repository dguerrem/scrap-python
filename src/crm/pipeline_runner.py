"""
Gestión de ejecución de la pipeline desde el CRM.

En local: lanza un subproceso con el script correspondiente.
En cloud (Turso): no puede ejecutar Playwright — muestra aviso de GitHub Actions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_PATH = DATA_DIR / "pipeline_run.log"
STATUS_PATH = DATA_DIR / "pipeline_status.json"
PROFILE_PATH = DATA_DIR / "active_profile.json"


def is_cloud() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL"))


def launch(profile: dict, mode: str) -> dict:
    """
    Lanza la pipeline en background.

    mode: 'scraper' | 'enricher' | 'pipeline'
    Retorna el dict de estado inicial.
    """
    if is_cloud():
        raise RuntimeError("cloud")

    DATA_DIR.mkdir(exist_ok=True)

    # Guardar el perfil en un fichero temporal para que el script lo lea
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    # Determinar ejecutable Python (mismo venv que el CRM)
    python = sys.executable

    cities = profile.get("ciudades", [])
    cities_arg = ",".join(cities) if cities else None

    if mode == "scraper":
        cmd = [python, str(PROJECT_ROOT / "run_scraper.py"), "--headless",
               "--profile", str(PROFILE_PATH)]
        if cities_arg:
            cmd += ["--cities", cities_arg]
    elif mode == "enricher":
        cmd = [python, str(PROJECT_ROOT / "run_enricher.py"), "--headless"]
    else:  # pipeline
        cmd = [python, str(PROJECT_ROOT / "run_pipeline.py"), "--headless",
               "--profile", str(PROFILE_PATH)]
        if cities_arg:
            cmd += ["--cities", cities_arg]

    log_file = open(LOG_PATH, "w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
    )

    status = {
        "pid": proc.pid,
        "mode": mode,
        "profile_nombre": profile.get("nombre", "Manual"),
        "started": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return status


def get_status() -> dict | None:
    """Retorna el estado del último proceso, actualizando si ya terminó."""
    if not STATUS_PATH.exists():
        return None

    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    if status.get("status") == "running":
        pid = status.get("pid", 0)
        alive = _pid_alive(pid)
        if not alive:
            status["status"] = "completed"
            status["finished"] = datetime.now().isoformat(timespec="seconds")
            STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")

    return status


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


def kill_current() -> bool:
    """Intenta matar el proceso activo. Retorna True si había proceso."""
    status = get_status()
    if not status or status.get("status") != "running":
        return False
    pid = status.get("pid", 0)
    try:
        os.kill(pid, 15)  # SIGTERM
    except OSError:
        pass
    status["status"] = "cancelled"
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return True


def get_log_tail(n: int = 40) -> str:
    """Últimas n líneas del log."""
    if not LOG_PATH.exists():
        return ""
    lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def clear_status():
    """Borra el fichero de estado (para empezar de nuevo)."""
    if STATUS_PATH.exists():
        STATUS_PATH.unlink()
