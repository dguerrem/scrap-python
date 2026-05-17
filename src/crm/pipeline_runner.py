"""
Gestión de ejecución de la pipeline desde el CRM.

En local: lanza un subproceso con el script correspondiente.
En cloud (Turso): no puede ejecutar Playwright — muestra aviso de GitHub Actions.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_PATH = DATA_DIR / "pipeline_run.log"
STATUS_PATH = DATA_DIR / "pipeline_status.json"
PROFILE_PATH = DATA_DIR / "active_profile.json"


def is_cloud() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL"))


def _make_run_id(profile_nombre: str) -> str:
    """Genera un run_id único: YYYYMMDD-HHMM-nombre-perfil."""
    now = datetime.now()
    ts = now.strftime("%Y%m%d-%H%M")
    clean = re.sub(r"[^\w\-]", "-", profile_nombre.lower()).strip("-")
    clean = re.sub(r"-{2,}", "-", clean)[:30]
    return f"{ts}-{clean}"


def launch(profile: dict, mode: str) -> dict:
    """
    Lanza la pipeline en background.

    mode: 'scraper' | 'enricher' | 'pipeline'
    Retorna el dict de estado inicial.
    """
    if is_cloud():
        raise RuntimeError("cloud")

    DATA_DIR.mkdir(exist_ok=True)

    # Generar run_id y añadirlo al perfil
    run_id = _make_run_id(profile.get("nombre", "manual"))
    profile = {**profile, "run_id": run_id}

    # Guardar perfil con run_id para que el script lo lea
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    python = sys.executable
    cities = profile.get("ciudades", [])
    cities_arg = ",".join(cities) if cities else None

    if mode == "scraper":
        cmd = [python, str(PROJECT_ROOT / "run_scraper.py"), "--headless",
               "--profile", str(PROFILE_PATH)]
        if cities_arg:
            cmd += ["--cities", cities_arg]
    elif mode == "enricher":
        cmd = [python, str(PROJECT_ROOT / "run_enricher.py"), "--headless",
               "--run-id", run_id]
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

    # Paths de los ficheros que generará esta ejecución
    runs_dir = DATA_DIR / "runs"
    output_files = {}
    if mode in ("scraper", "pipeline"):
        output_files["raw_json"] = str(runs_dir / f"{run_id}-raw.json")
        output_files["raw_csv"] = str(runs_dir / f"{run_id}-raw.csv")
    if mode in ("enricher", "pipeline"):
        output_files["enriched_json"] = str(runs_dir / f"{run_id}-enriched.json")
        output_files["enriched_csv"] = str(runs_dir / f"{run_id}-enriched.csv")

    status = {
        "pid": proc.pid,
        "mode": mode,
        "run_id": run_id,
        "profile_nombre": profile.get("nombre", "Manual"),
        "started": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "output_files": output_files,
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
    # Try to reap zombie child first (Popen child in same process tree)
    try:
        wpid, _ = os.waitpid(pid, os.WNOHANG)
        if wpid != 0:
            return False  # Reaped → process finished
        return True  # wpid == 0 → still running
    except ChildProcessError:
        pass  # Not our child — fall through
    except OSError:
        return False

    # PID exists? os.kill(0) succeeds even for zombies, so also check ps
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False

    try:
        r = subprocess.run(
            ["ps", "-p", str(pid), "-o", "state="],
            capture_output=True, text=True, timeout=2,
        )
        return not r.stdout.strip().startswith("Z")
    except Exception:
        return True


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


# ─── Cloud: GitHub Actions ───────────────────────────────────────

def _gh_request(method: str, path: str, data: dict | None = None) -> dict | None:
    """Helper para llamadas a la GitHub API."""
    token = os.environ.get("GITHUB_PAT", "")
    repo = os.environ.get("GITHUB_REPO", "")
    if not token or not repo:
        return None

    url = f"https://api.github.com/repos/{repo}{path}"
    body = json.dumps(data).encode("utf-8") if data else None

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body else {}),
        },
        method=method,
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API {e.code}: {e.read().decode()[:200]}")


def cloud_configured() -> bool:
    """True si GITHUB_PAT y GITHUB_REPO están configurados."""
    return bool(os.environ.get("GITHUB_PAT") and os.environ.get("GITHUB_REPO"))


def launch_cloud(profile: dict, mode: str) -> dict:
    """Dispara el workflow pipeline.yml vía workflow_dispatch."""
    if not cloud_configured():
        raise RuntimeError(
            "Configura GITHUB_PAT y GITHUB_REPO en los secrets de Streamlit."
        )

    cities = profile.get("ciudades", [])

    _gh_request("POST", "/actions/workflows/pipeline.yml/dispatches", {
        "ref": "main",
        "inputs": {
            "mode": mode,
            "profile_json": json.dumps(profile, ensure_ascii=False),
            "cities": ",".join(cities) if cities else "",
        },
    })

    return {
        "status": "dispatched",
        "mode": mode,
        "profile_nombre": profile.get("nombre", "Manual"),
        "dispatched_at": datetime.now().isoformat(timespec="seconds"),
    }


def get_cloud_status() -> dict | None:
    """Estado del último workflow run de pipeline.yml."""
    if not cloud_configured():
        return None

    try:
        data = _gh_request("GET", "/actions/workflows/pipeline.yml/runs?per_page=1")
    except Exception:
        return None

    if not data:
        return None

    runs = data.get("workflow_runs", [])
    if not runs:
        return None

    run = runs[0]
    gh_status = run.get("status", "")
    gh_conclusion = run.get("conclusion")

    if gh_status in ("queued", "in_progress", "waiting", "pending"):
        status = "running"
    elif gh_conclusion == "success":
        status = "completed"
    elif gh_conclusion == "cancelled":
        status = "cancelled"
    else:
        status = "failed"

    return {
        "status": status,
        "gh_status": gh_status,
        "gh_conclusion": gh_conclusion,
        "html_url": run.get("html_url", ""),
        "created_at": run.get("created_at", ""),
        "updated_at": run.get("updated_at", ""),
    }
