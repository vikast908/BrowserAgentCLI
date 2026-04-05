"""SQLite-backed run history storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from browseagent.llm.schemas import RunResultSchema


class RunStore:
    """Stores and retrieves agent run history using SQLite."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "runs.db"
        self._init_db()

    def _init_db(self) -> None:
        """Create the runs table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_steps INTEGER,
                    elapsed_seconds REAL,
                    data_json TEXT,
                    plan_json TEXT,
                    started_at TEXT,
                    finished_at TEXT
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def save_run(self, result: RunResultSchema) -> None:
        """Save a completed run to the database."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                    (run_id, task, status, total_steps, elapsed_seconds,
                     data_json, plan_json, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.task,
                    result.status,
                    result.total_steps,
                    result.elapsed_seconds,
                    json.dumps(result.data, default=str),
                    result.plan.model_dump_json() if result.plan else "{}",
                    result.started_at.isoformat() if result.started_at else None,
                    result.finished_at.isoformat() if result.finished_at else None,
                ),
            )

        # Also save the full result as JSON in the run folder
        run_dir = self.data_dir / result.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        results_file = run_dir / "results.json"
        with open(results_file, "w") as f:
            json.dump(result.data, f, indent=2, default=str)

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent runs, newest first."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT run_id, task, status, total_steps, elapsed_seconds, started_at "
                "FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get full details of a specific run."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()

        if not row:
            return None

        result = dict(row)
        if result.get("data_json"):
            result["data"] = json.loads(result["data_json"])
        if result.get("plan_json"):
            result["plan"] = json.loads(result["plan_json"])
        return result
