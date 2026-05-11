import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ambig_swe_useful_info.bed.planner import BEDAmbigRunner
from ambig_swe_useful_info.config import BEDConfig
from ambig_swe_useful_info.data.loader import load_ambig_swe_jsonl
from ambig_swe_useful_info.direct.runner import DirectAmbigRunner
from ambig_swe_useful_info.eval.metrics import evaluate, format_report
from ambig_swe_useful_info.eval.useful_info import info_coverage_per_turn
from ambig_swe_useful_info.llm.mock_backend import MockBackend


def test_coverage_per_turn_monotone():
    dialogue = [
        {"role": "user", "content": "hidden"},
        {"role": "agent", "content": "q1?"},
        {"role": "user", "content": "item one"},
        {"role": "agent", "content": "q2?"},
        {"role": "user", "content": "item two"},
        {"role": "agent", "content": "q3?"},
        {"role": "user", "content": "item three"},
    ]
    items = ["item one", "item two", "item three"]
    out = info_coverage_per_turn(dialogue, items, max_turns=3)
    assert len(out) == 3
    ratios = [r["cumulative_ratio"] for r in out]
    assert ratios == sorted(ratios)
    assert ratios[-1] == 1.0


def test_evaluate_end_to_end(tmp_path: Path, sample_dataset_path: Path):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    bed_runner = BEDAmbigRunner(
        MockBackend(), BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=2)
    )
    direct_runner = DirectAmbigRunner(MockBackend(), BEDConfig(max_turns=2))

    bed_path = tmp_path / "bed.jsonl"
    direct_path = tmp_path / "direct.jsonl"
    for path, runner in [(bed_path, bed_runner), (direct_path, direct_runner)]:
        with path.open("w", encoding="utf-8") as h:
            for t in tasks:
                row = asdict(runner.run_task(t))
                h.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = evaluate(
        bed_path=bed_path,
        direct_path=direct_path,
        dataset_path=sample_dataset_path,
        max_turns=2,
    )
    assert summary["n_tasks"] == 1
    assert "ttr_mean" in summary["bed"]
    assert "recovery_rate" in summary["bed"]
    assert "info_coverage" in summary["bed"]
    assert "coverage_curve" in summary["bed"]
    assert len(summary["bed"]["coverage_curve"]) == 2
    assert summary["per_task"][0]["bed_ttr"] == summary["per_task"][0]["direct_ttr"]
    bed_curve = summary["per_task"][0]["bed_info_coverage_per_turn"]
    assert len(bed_curve) == 2
    assert bed_curve == sorted(bed_curve)

    report = format_report(summary)
    assert "Useful-info recovery evaluation" in report
    assert "ttr_mean" in report
    assert "TTR derived from useful-info coverage" in report
    assert "Useful-info coverage curve" in report


def test_evaluate_preserves_duplicate_task_rows(tmp_path: Path, sample_record: dict):
    dataset_path = tmp_path / "ambig_swe_10_like.jsonl"
    dataset_path.write_text(
        "\n".join(json.dumps(sample_record) for _ in range(2)) + "\n",
        encoding="utf-8",
    )
    tasks = load_ambig_swe_jsonl(dataset_path)
    bed_runner = BEDAmbigRunner(
        MockBackend(), BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=1)
    )
    direct_runner = DirectAmbigRunner(MockBackend(), BEDConfig(max_turns=1))

    bed_path = tmp_path / "bed.jsonl"
    direct_path = tmp_path / "direct.jsonl"
    for path, runner in [(bed_path, bed_runner), (direct_path, direct_runner)]:
        with path.open("w", encoding="utf-8") as h:
            for task in tasks:
                h.write(json.dumps(asdict(runner.run_task(task)), ensure_ascii=False) + "\n")

    summary = evaluate(
        bed_path=bed_path,
        direct_path=direct_path,
        dataset_path=dataset_path,
        max_turns=1,
    )

    assert summary["n_tasks"] == 2
    assert [row["row_occurrence"] for row in summary["per_task"]] == [1, 2]


def test_evaluate_reads_raw_pretty_runner_output(
    tmp_path: Path, sample_dataset_path: Path
):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    bed_runner = BEDAmbigRunner(
        MockBackend(), BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=1)
    )
    direct_runner = DirectAmbigRunner(MockBackend(), BEDConfig(max_turns=1))

    bed_row = asdict(bed_runner.run_task(tasks[0]))
    direct_row = asdict(direct_runner.run_task(tasks[0]))

    bed_path = tmp_path / "bed_raw.jsonl"
    direct_path = tmp_path / "direct_raw.jsonl"
    bed_path.write_text(
        json.dumps(bed_row, ensure_ascii=False, indent=2) + "\n\n",
        encoding="utf-8",
    )
    direct_path.write_text(
        json.dumps(direct_row, ensure_ascii=False, indent=2) + "\n\n",
        encoding="utf-8",
    )

    summary = evaluate(
        bed_path=bed_path,
        direct_path=direct_path,
        dataset_path=sample_dataset_path,
        max_turns=1,
    )

    assert summary["n_tasks"] == 1
    assert summary["per_task"][0]["task_id"] == tasks[0].task_id


def test_evaluate_rejects_raw_output_with_trailing_fragment(
    tmp_path: Path, sample_dataset_path: Path
):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    bed_runner = BEDAmbigRunner(
        MockBackend(), BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=1)
    )
    direct_runner = DirectAmbigRunner(MockBackend(), BEDConfig(max_turns=1))

    bed_path = tmp_path / "bed_raw.jsonl"
    direct_path = tmp_path / "direct_raw.jsonl"
    bed_path.write_text(
        json.dumps(asdict(bed_runner.run_task(tasks[0])), ensure_ascii=False, indent=2)
        + "\n\n"
        + '"distribution"\n',
        encoding="utf-8",
    )
    direct_path.write_text(
        json.dumps(asdict(direct_runner.run_task(tasks[0])), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected JSON object|Invalid JSON output file"):
        evaluate(
            bed_path=bed_path,
            direct_path=direct_path,
            dataset_path=sample_dataset_path,
            max_turns=1,
        )


def test_evaluate_fails_on_incomplete_paired_outputs(tmp_path: Path, sample_record: dict):
    dataset_path = tmp_path / "ambig_swe_10_like.jsonl"
    dataset_path.write_text(
        "\n".join(json.dumps(sample_record) for _ in range(2)) + "\n",
        encoding="utf-8",
    )
    tasks = load_ambig_swe_jsonl(dataset_path)
    runner = BEDAmbigRunner(
        MockBackend(), BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=1)
    )

    bed_path = tmp_path / "bed.jsonl"
    direct_path = tmp_path / "direct.jsonl"
    bed_path.write_text(
        "\n".join(
            json.dumps(asdict(runner.run_task(task)), ensure_ascii=False)
            for task in tasks
        )
        + "\n",
        encoding="utf-8",
    )
    direct_path.write_text(
        json.dumps(asdict(runner.run_task(tasks[0])), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Direct missing"):
        evaluate(
            bed_path=bed_path,
            direct_path=direct_path,
            dataset_path=dataset_path,
            max_turns=1,
        )
