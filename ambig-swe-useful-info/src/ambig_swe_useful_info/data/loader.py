from __future__ import annotations

from pathlib import Path

from ambig_swe_useful_info.bed.utils import iter_jsonl_records
from ambig_swe_useful_info.schemas import AmbigSWETask


def load_ambig_swe_jsonl(
    path: str | Path,
) -> list[AmbigSWETask]:
    records: list[AmbigSWETask] = []
    for raw in iter_jsonl_records(Path(path)):
        task_id = raw.get("task_id", "")
        records.append(
            AmbigSWETask(
                task_id=task_id,
                repo=raw.get("repo", ""),
                hidden_issue=raw.get("hidden_issue", ""),
                full_issue=raw.get("full_issue", ""),
                useful_info_items=[
                    str(item).strip()
                    for item in raw.get("useful_info_items", [])
                    if str(item).strip()
                ],
                useful_info_explanations=[
                    item
                    for item in raw.get("useful_info_explanations", [])
                    if isinstance(item, dict)
                ],
                useful_info_sufficiency=str(raw.get("useful_info_sufficiency", "")).strip(),
                raw=raw,
            )
        )
    return records

