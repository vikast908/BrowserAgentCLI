"""Export run results to CSV and JSON files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def export_csv(data: list[dict[str, Any]], output_path: Path | str) -> Path:
    """Export a list of records to a CSV file.

    Returns the path to the created file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not data:
        path.write_text("")
        return path

    headers = list(data[0].keys())

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in data:
            writer.writerow({k: str(v) for k, v in row.items()})

    return path


def export_json(data: list[dict[str, Any]], output_path: Path | str) -> Path:
    """Export a list of records to a JSON file.

    Returns the path to the created file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    return path
