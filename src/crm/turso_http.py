"""
Lightweight HTTP client for Turso/libsql.
Replaces libsql-experimental — zero native build dependencies.
Uses the Turso /v2/pipeline HTTP API.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.error import HTTPError


# ── Row (sqlite3.Row-compatible) ─────────────────────────────────────────

class Row:
    """Supports row["col"], row[0], dict(row), len(row)."""
    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols: list[str], vals: list):
        self._cols = cols
        self._vals = vals
        self._map = dict(zip(cols, vals))

    def __getitem__(self, key):
        return self._vals[key] if isinstance(key, int) else self._map[key]

    def __len__(self):
        return len(self._vals)

    def __iter__(self):
        return iter(self._vals)

    def keys(self):
        return list(self._cols)


# ── Cursor ───────────────────────────────────────────────────────────────

class _Cursor:
    """Minimal DB-API 2.0 cursor."""

    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self) -> list:
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    # sqlite3.Cursor es iterable, así que `for r in conn.execute(...)` funciona
    # en local y reventaba en cloud (BUG-5). Se implementa aquí para que las dos
    # capas se comporten igual y la trampa no pueda volver.
    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)


# ── Value conversion helpers ─────────────────────────────────────────────

def _to_arg(val):
    """Python value → Turso JSON arg."""
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": str(int(val))}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    return {"type": "text", "value": str(val)}


def _from_cell(cell: dict):
    """Turso JSON cell → Python value."""
    t = cell.get("type", "null")
    if t == "null":
        return None
    if t == "integer":
        return int(cell["value"])
    if t == "float":
        return float(cell["value"])
    return cell.get("value", "")


# ── Connection ───────────────────────────────────────────────────────────

_CHUNK = 500  # max statements per pipeline request


class TursoConnection:
    """
    sqlite3-compatible connection that talks to Turso via its HTTP
    pipeline API.  Supports execute, executemany, commit, close, and
    row_factory.
    """

    def __init__(self, url: str, auth_token: str = ""):
        base = url.replace("libsql://", "https://")
        self._endpoint = f"{base}/v2/pipeline"
        self._token = auth_token
        self.row_factory = None  # set externally (e.g. sqlite3.Row)

    # -- public API -------------------------------------------------------

    def execute(self, sql: str, params=()) -> _Cursor:
        """Run a single SQL statement."""
        stmt = {"sql": sql, "args": [_to_arg(p) for p in params]}
        results = self._pipeline([stmt])
        return self._to_cursor(results[0]) if results else _Cursor([])

    def executemany(self, sql: str, seq_of_params) -> _Cursor:
        """Run the same SQL with many parameter sets (batched)."""
        params_list = list(seq_of_params)
        for i in range(0, len(params_list), _CHUNK):
            chunk = params_list[i : i + _CHUNK]
            stmts = [
                {"sql": sql, "args": [_to_arg(p) for p in params]}
                for params in chunk
            ]
            self._pipeline(stmts)
        return _Cursor([])

    def commit(self):
        pass  # HTTP auto-commits each statement

    def close(self):
        pass

    # -- internals --------------------------------------------------------

    def _pipeline(self, stmts: list[dict]) -> list[dict]:
        """Send a list of statements to Turso's /v2/pipeline endpoint."""
        reqs = [{"type": "execute", "stmt": s} for s in stmts]
        reqs.append({"type": "close"})

        data = json.dumps({"requests": reqs}).encode()
        req = urllib.request.Request(
            self._endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read())
        except HTTPError as e:
            raise RuntimeError(f"Turso HTTP {e.code}: {e.read().decode()}")

        exec_results = []
        for item in body.get("results", []):
            if item.get("type") == "error":
                msg = item.get("error", {}).get("message", str(item))
                raise RuntimeError(f"Turso SQL error: {msg}")
            r = item.get("response", {})
            if r.get("type") == "execute":
                exec_results.append(r["result"])
        return exec_results

    def _to_cursor(self, result: dict) -> _Cursor:
        cols = [c["name"] for c in result.get("cols", [])]
        rows = []
        for raw in result.get("rows", []):
            vals = [_from_cell(cell) for cell in raw]
            rows.append(Row(cols, vals) if self.row_factory else tuple(vals))
        return _Cursor(rows)
