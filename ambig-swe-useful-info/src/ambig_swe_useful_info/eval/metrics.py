"""Aggregate useful-info recovery metrics across paired BED / Direct runs.

Reads both result jsonl files plus the useful-info annotated dataset jsonl,
then computes per-task useful-info coverage (final + per-turn cumulative).
TTR is derived from coverage: the first turn at which cumulative coverage
reaches 1.0 (censored at max_turns + 1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ambig_swe_useful_info.bed.utils import iter_jsonl_records
from ambig_swe_useful_info.data.loader import load_ambig_swe_jsonl
from ambig_swe_useful_info.eval.useful_info import (
    info_coverage_per_turn,
)
RowKey = tuple[str, int]


def _row_key(task_id: str, occurrence: int) -> RowKey:
    return task_id, occurrence


def _load_runs(path: Path) -> dict[RowKey, dict]:
    runs: dict[RowKey, dict] = {}
    counts: dict[str, int] = {}
    for row in iter_jsonl_records(path):
        task_id = row.get("task_id", "")
        if task_id:
            counts[task_id] = counts.get(task_id, 0) + 1
            runs[_row_key(task_id, counts[task_id])] = row
    return runs


def _tasks_by_row_key(dataset_path: str | Path) -> tuple[dict[RowKey, Any], list[RowKey]]:
    tasks: dict[RowKey, Any] = {}
    keys: list[RowKey] = []
    counts: dict[str, int] = {}
    for task in load_ambig_swe_jsonl(dataset_path):
        counts[task.task_id] = counts.get(task.task_id, 0) + 1
        key = _row_key(task.task_id, counts[task.task_id])
        tasks[key] = task
        keys.append(key)
    return tasks, keys


def _padded_curve(per_turn: list[dict], max_turns: int) -> list[float]:
    """Length-max_turns list of cumulative ratios; pad missing tail with last value."""
    ratios = [float(r["cumulative_ratio"]) for r in per_turn]
    if not ratios:
        return [0.0] * max_turns
    if len(ratios) >= max_turns:
        return ratios[:max_turns]
    return ratios + [ratios[-1]] * (max_turns - len(ratios))


def _first_full_turn(per_turn: list[dict], max_turns: int) -> int:
    for r in per_turn:
        if r["cumulative_ratio"] >= 1.0 - 1e-9:
            return int(r["turn"])
    return max_turns + 1


def evaluate(
    bed_path: str | Path,
    direct_path: str | Path,
    dataset_path: str | Path,
    max_tasks: int | None = None,
    max_turns: int = 5,
) -> dict[str, Any]:
    bed_runs = _load_runs(Path(bed_path))
    direct_runs = _load_runs(Path(direct_path))
    tasks, dataset_keys = _tasks_by_row_key(dataset_path)
    expected = dataset_keys[:max_tasks] if max_tasks is not None else dataset_keys
    missing_bed = [key for key in expected if key not in bed_runs]
    missing_direct = [key for key in expected if key not in direct_runs]
    if missing_bed or missing_direct:
        parts = []
        if missing_bed:
            parts.append(f"BED missing {len(missing_bed)} row(s): {missing_bed[:5]}")
        if missing_direct:
            parts.append(f"Direct missing {len(missing_direct)} row(s): {missing_direct[:5]}")
        raise ValueError("; ".join(parts))

    shared = list(expected)
    if max_tasks is not None:
        shared = shared[:max_tasks]

    per_task: list[dict[str, Any]] = []

    for row_key in shared:
        tid, occurrence = row_key
        task = tasks[row_key]
        bed = bed_runs[row_key]
        direct = direct_runs[row_key]

        items = list(task.useful_info_items)

        bed_per_turn = info_coverage_per_turn(bed["dialogue"], items, max_turns)
        direct_per_turn = info_coverage_per_turn(direct["dialogue"], items, max_turns)

        bed_curve = _padded_curve(bed_per_turn, max_turns)
        direct_curve = _padded_curve(direct_per_turn, max_turns)

        bed_coverage = bed_curve[-1] if bed_curve else 0.0
        direct_coverage = direct_curve[-1] if direct_curve else 0.0

        bed_first_full = _first_full_turn(bed_per_turn, max_turns)
        direct_first_full = _first_full_turn(direct_per_turn, max_turns)

        per_task.append(
            {
                "task_id": tid,
                "row_occurrence": occurrence,
                "n_useful_info_items": len(items),
                "bed_info_coverage": bed_coverage,
                "direct_info_coverage": direct_coverage,
                "bed_info_coverage_per_turn": bed_curve,
                "direct_info_coverage_per_turn": direct_curve,
                "bed_info_coverage_per_turn_detail": bed_per_turn,
                "direct_info_coverage_per_turn_detail": direct_per_turn,
                # TTR derived from coverage: first turn cumulative_ratio = 1.0
                "bed_ttr": bed_first_full,
                "direct_ttr": direct_first_full,
                "bed_recovered": bed_first_full <= max_turns,
                "direct_recovered": direct_first_full <= max_turns,
                "bed_atc": bed.get("metrics", {}).get("atc", 0.0),
                "direct_atc": direct.get("metrics", {}).get("atc", 0.0),
                "bed_idk": bed.get("metrics", {}).get("n_idk_responses", 0),
                "direct_idk": direct.get("metrics", {}).get("n_idk_responses", 0),
            }
        )

    summary = _aggregate(per_task, max_turns)
    summary["per_task"] = per_task
    return summary


def _aggregate(per_task: list[dict], max_turns: int) -> dict[str, Any]:
    n = len(per_task)
    zero_curve = [0.0] * max_turns
    if n == 0:
        return {
            "n_tasks": 0,
            "max_turns": max_turns,
            "bed": {"info_coverage": 0.0, "atc": 0.0, "idk_per_task": 0.0,
                    "ttr_mean": 0.0, "recovery_rate": 0.0,
                    "coverage_curve": list(zero_curve)},
            "direct": {"info_coverage": 0.0, "atc": 0.0, "idk_per_task": 0.0,
                       "ttr_mean": 0.0, "recovery_rate": 0.0,
                       "coverage_curve": list(zero_curve)},
        }

    def mean(field: str) -> float:
        return sum(row[field] for row in per_task) / n

    def rate(field: str) -> float:
        return sum(1 for row in per_task if row[field]) / n

    def curve(field: str) -> list[float]:
        return [
            sum(row[field][k] for row in per_task) / n
            for k in range(max_turns)
        ]

    return {
        "n_tasks": n,
        "max_turns": max_turns,
        "bed": {
            "info_coverage": mean("bed_info_coverage"),
            "atc": mean("bed_atc"),
            "idk_per_task": mean("bed_idk"),
            "ttr_mean": mean("bed_ttr"),
            "recovery_rate": rate("bed_recovered"),
            "coverage_curve": curve("bed_info_coverage_per_turn"),
        },
        "direct": {
            "info_coverage": mean("direct_info_coverage"),
            "atc": mean("direct_atc"),
            "idk_per_task": mean("direct_idk"),
            "ttr_mean": mean("direct_ttr"),
            "recovery_rate": rate("direct_recovered"),
            "coverage_curve": curve("direct_info_coverage_per_turn"),
        },
    }


def format_report(summary: dict[str, Any]) -> str:
    n = summary["n_tasks"]
    bed = summary["bed"]
    direct = summary["direct"]
    max_turns = summary.get("max_turns", 0)

    def delta(a: float, b: float) -> str:
        diff = a - b
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:.3f}"

    lines = []
    lines.append(
        f"Useful-info recovery evaluation over {n} tasks  (max_turns={max_turns}, "
        f"censored TTR={max_turns + 1};  TTR derived from useful-info coverage: first turn coverage=1.0)\n"
    )
    lines.append(f"{'Metric':<26}  {'BED':>8}  {'Direct':>8}  {'Delta (BED-Direct)':>20}")
    lines.append(f"{'-' * 26}  {'-' * 8}  {'-' * 8}  {'-' * 16}")
    lines.append(
        f"{'ttr_mean':<26}  {bed['ttr_mean']:>8.2f}  "
        f"{direct['ttr_mean']:>8.2f}  {delta(bed['ttr_mean'], direct['ttr_mean']):>16}    (lower is better)"
    )
    lines.append(
        f"{'recovery_rate':<26}  {bed['recovery_rate']:>8.3f}  "
        f"{direct['recovery_rate']:>8.3f}  {delta(bed['recovery_rate'], direct['recovery_rate']):>16}"
    )
    lines.append(
        f"{'useful_info_coverage':<26}  {bed['info_coverage']:>8.3f}  "
        f"{direct['info_coverage']:>8.3f}  {delta(bed['info_coverage'], direct['info_coverage']):>16}"
    )
    lines.append(
        f"{'atc_mean':<26}  {bed['atc']:>8.2f}  "
        f"{direct['atc']:>8.2f}  {delta(bed['atc'], direct['atc']):>16}    (lower is better)"
    )
    lines.append(
        f"{'idk_per_task':<26}  {bed['idk_per_task']:>8.2f}  "
        f"{direct['idk_per_task']:>8.2f}  {delta(bed['idk_per_task'], direct['idk_per_task']):>16}"
    )
    lines.append("")

    lines.append("Useful-info coverage curve (cumulative ratio at each turn)")
    header = "turn".ljust(10) + "  ".join(f"{k + 1:>6}" for k in range(max_turns))
    lines.append(header)
    bed_row = "BED".ljust(10) + "  ".join(f"{bed['coverage_curve'][k]:>6.3f}" for k in range(max_turns))
    direct_row = "Direct".ljust(10) + "  ".join(f"{direct['coverage_curve'][k]:>6.3f}" for k in range(max_turns))
    lines.append(bed_row)
    lines.append(direct_row)
    return "\n".join(lines)

