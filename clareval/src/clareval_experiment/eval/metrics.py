from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from clareval_experiment.bed.utils import iter_jsonl_records


def evaluate_predictions(path: str | Path) -> dict:
    by_task_group = defaultdict(list)
    overall = []

    for row in iter_jsonl_records(Path(path)):
        metrics = row.get("metrics", {})
        item = {
            "completion_rate": metrics.get("completion_rate", 0.0),
            "efficiency": metrics.get("efficiency_ratio", 0.0),
            "atc": metrics.get("atc", 0.0),
            "simulator_answered_count": metrics.get("simulator_answered_count", 0.0),
            "simulator_answer_rate": metrics.get("simulator_answer_rate", 0.0),
            "unresolved": 1.0 if metrics.get("unresolved", False) else 0.0,
        }
        overall.append(item)
        group = row.get("task_group") or (
            f"{row.get('fuzzy_type', 'unknown')} / {row.get('difficulty', 'unknown')}"
        )
        by_task_group[group].append(item)

    def summarize(items: list[dict]) -> dict:
        if not items:
            return {
                "n": 0,
                "completion_rate": 0.0,
                "efficiency": 0.0,
                "atc": 0.0,
                "simulator_answered_count": 0.0,
                "simulator_answer_rate": 0.0,
                "unresolved_rate": 0.0,
            }
        return {
            "n": len(items),
            "completion_rate": sum(item["completion_rate"] for item in items) / len(items),
            "efficiency": sum(item["efficiency"] for item in items) / len(items),
            "atc": sum(item["atc"] for item in items) / len(items),
            "simulator_answered_count": sum(
                item["simulator_answered_count"] for item in items
            ) / len(items),
            "simulator_answer_rate": sum(
                item["simulator_answer_rate"] for item in items
            ) / len(items),
            "unresolved_rate": sum(item["unresolved"] for item in items) / len(items),
        }

    return {
        "overall": summarize(overall),
        "by_task_group": {
            key: summarize(values)
            for key, values in sorted(by_task_group.items())
        },
    }


def format_report(summary: dict) -> str:
    lines = []
    lines.append("ClarEval Experiment evaluation summary")
    lines.append("=" * 60)
    lines.append(_format_row("OVERALL", summary.get("overall", {})))

    lines.append("")
    lines.append("By task group")
    for group, metrics in summary.get("by_task_group", {}).items():
        lines.append(_format_row(group, metrics))

    return "\n".join(lines)


def _format_row(label: str, metrics: dict) -> str:
    return (
        f"- {label}: n={metrics.get('n', 0)}, "
        f"completion={metrics.get('completion_rate', 0.0):.3f}, "
        f"efficiency={metrics.get('efficiency', 0.0):.3f}, "
        f"ATC={metrics.get('atc', 0.0):.3f}, "
        f"sim_answered={metrics.get('simulator_answered_count', 0.0):.3f}, "
        f"sim_answer_rate={metrics.get('simulator_answer_rate', 0.0):.3f}, "
        f"unresolved={metrics.get('unresolved_rate', 0.0):.3f}"
    )
