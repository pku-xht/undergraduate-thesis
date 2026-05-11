import json
from pathlib import Path

from ambig_swe_useful_info.cli import build_parser
from ambig_swe_useful_info.eval.metrics import evaluate


def test_cli_run_writes_compact_jsonl_and_evaluate_reads_it(
    tmp_path: Path,
    sample_dataset_path: Path,
):
    direct_path = tmp_path / "direct.jsonl"
    bed_path = tmp_path / "bed.jsonl"

    for runner, output in [("direct", direct_path), ("bed", bed_path)]:
        args = build_parser().parse_args(
            [
                "run",
                "--dataset",
                str(sample_dataset_path),
                "--output",
                str(output),
                "--runner",
                runner,
                "--backend",
                "mock",
                "--max-turns",
                "1",
                "--verbose-turns",
            ]
        )
        args.func(args)

        lines = output.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["runner"] == runner
        assert row["metadata"]["request_timeout"] is None

    summary = evaluate(
        bed_path=bed_path,
        direct_path=direct_path,
        dataset_path=sample_dataset_path,
        max_turns=1,
    )
    assert summary["n_tasks"] == 1
