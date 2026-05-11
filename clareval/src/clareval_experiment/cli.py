from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from tqdm import tqdm

from clareval_experiment.bed.planner import BEDClarEvalRunner
from clareval_experiment.bed.utils import iter_jsonl_records
from clareval_experiment.config import BEDConfig
from clareval_experiment.data.loader import load_clareval_jsonl
from clareval_experiment.direct.runner import DirectClarRunner
from clareval_experiment.eval.metrics import evaluate_predictions, format_report
from clareval_experiment.llm.mock_backend import MockBackend

# Default rolling metric summary interval for small experiment subsets.
_DEFAULT_SUMMARY_INTERVAL = 5


def build_backend(name: str, model: str, base_url: str | None, api_key: str | None):
    if name == "openai":
        from clareval_experiment.llm.openai_backend import OpenAIBackend
        return OpenAIBackend(model, base_url=base_url, api_key=api_key)
    return MockBackend()


def sanitize_jsonl_for_resume(path: Path) -> tuple[set[str], bool]:
    completed: set[str] = set()
    if not path.exists():
        return completed, False

    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    valid_records: list[dict] = []
    truncated = False
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            idx = end_idx
            valid_records.append(obj)
        except json.JSONDecodeError:
            truncated = True
            break

    for row in valid_records:
        task_id = row.get("task_id")
        if task_id:
            completed.add(task_id)

    if truncated:
        with path.open("w", encoding="utf-8") as handle:
            for row in valid_records:
                handle.write(json.dumps(row, ensure_ascii=False, indent=2) + "\n\n")

    return completed, truncated


def load_completed_task_ids(path: Path) -> set[str]:
    """Read completed task ids from a possibly partial result file.

    This is a non-mutating companion to sanitize_jsonl_for_resume(), useful for
    tests and quick inspection. It stops at the first invalid JSON object.
    """
    completed: set[str] = set()
    if not path.exists():
        return completed

    text = path.read_text(encoding="utf-8", errors="replace")
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(text):
            break
        try:
            row, end_idx = decoder.raw_decode(text, idx)
            idx = end_idx
        except json.JSONDecodeError:
            break
        task_id = row.get("task_id") if isinstance(row, dict) else None
        if task_id:
            completed.add(task_id)
    return completed


def _fmt_summary(counter: dict, total: int, elapsed: float) -> str:
    """One-line running aggregate shown in the tqdm bar description."""
    n = counter["done"]
    if n == 0:
        return "ClarEval Experiment"
    avg_completion = counter["completion_sum"] / n
    rate = n / elapsed if elapsed > 0 else 0
    return f"completion={avg_completion:.2f} {rate:.2f}t/s"


def _build_run_metadata(args: argparse.Namespace) -> dict:
    return {
        "runner": args.runner,
        "backend": args.backend,
        "model": args.model,
        "simulator_model": args.simulator_model or args.model,
        "evaluator_model": args.evaluator_model or args.simulator_model or args.model,
        "dataset": args.dataset,
        "max_turns": args.max_turns,
        "num_hypotheses": args.num_hypotheses,
        "num_candidates": args.num_candidates,
        "concurrency": args.concurrency,
    }


def _write_progress_file(
    path: Path | None,
    *,
    status: str,
    counter: dict,
    task_group_buckets: dict,
    total: int,
    started_at: float,
    metadata: dict,
    last_task_id: str | None = None,
) -> None:
    if path is None:
        return

    done = counter["done"]
    elapsed = time.time() - started_at
    progress = {
        "status": status,
        "metadata": metadata,
        "total": total,
        "done": done,
        "errors": counter["errors"],
        "remaining": max(total - done - counter["errors"], 0),
        "elapsed_seconds": round(elapsed, 2),
        "tasks_per_second": round(done / elapsed, 4) if elapsed > 0 else 0.0,
        "last_completed_task_id": last_task_id,
        "averages": {
            "completion_rate": counter["completion_sum"] / done if done else 0.0,
            "atc": counter["atc_sum"] / done if done else 0.0,
            "efficiency": counter["eff_sum"] / done if done else 0.0,
            "simulator_answered_count": counter["sim_answered_sum"] / done if done else 0.0,
            "simulator_answer_rate": counter["sim_answer_rate_sum"] / done if done else 0.0,
            "unresolved_rate": counter["unresolved_sum"] / done if done else 0.0,
        },
        "by_task_group": {},
    }
    for group, bucket in sorted(task_group_buckets.items()):
        n = bucket["n"]
        progress["by_task_group"][group] = {
            "n": n,
            "completion_rate": bucket["completion"] / n if n else 0.0,
            "atc": bucket["atc"] / n if n else 0.0,
            "efficiency": bucket["eff"] / n if n else 0.0,
            "simulator_answered_count": bucket["sim_answered"] / n if n else 0.0,
            "simulator_answer_rate": bucket["sim_answer_rate"] / n if n else 0.0,
            "unresolved_rate": bucket["unresolved"] / n if n else 0.0,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_rolling_summary(counter: dict, task_group_buckets: dict) -> None:
    """Print a per-task-group breakdown of metrics collected so far."""
    n = counter["done"]
    sep = "-" * 62
    tqdm.write("")
    tqdm.write(f"  Rolling summary after {n} tasks")
    tqdm.write(f"  {sep}")
    tqdm.write(
        f"  {'Task group':<26}  {'n':>4}  {'Comp':>6}  {'ATC':>5}  "
        f"{'Ans':>5}  {'Unres':>6}"
    )
    tqdm.write(f"  {'-'*26}  {'-'*4}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*6}")
    for group, b in sorted(task_group_buckets.items()):
        if b["n"] == 0:
            continue
        bn = b["n"]
        tqdm.write(
            f"  {group:<26}  {bn:>4}  "
            f"{b['completion']/bn:>6.3f}  "
            f"{b['atc']/bn:>5.2f}  {b['sim_answered']/bn:>5.2f}  "
            f"{b['unresolved']/bn:>6.3f}"
        )
    overall_n = sum(b["n"] for b in task_group_buckets.values())
    if overall_n:
        tqdm.write(f"  {'-'*26}  {'-'*4}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*6}")
        tqdm.write(
            f"  {'OVERALL':<26}  {overall_n:>4}  "
            f"{counter['completion_sum']/n:>6.3f}  "
            f"{counter['atc_sum']/n:>5.2f}  {counter['sim_answered_sum']/n:>5.2f}  "
            f"{counter['unresolved_sum']/n:>6.3f}"
        )
    tqdm.write(f"  {sep}")
    tqdm.write("")


def build_runner(runner_name: str, backend, simulator_backend, evaluator_backend, args: argparse.Namespace):
    config = BEDConfig(
        num_hypotheses=args.num_hypotheses,
        num_candidates=args.num_candidates,
        max_turns=args.max_turns,
    )
    if runner_name == "direct":
        return DirectClarRunner(
            backend=backend,
            simulator_backend=simulator_backend,
            evaluator_backend=evaluator_backend,
            config=config,
        )
    return BEDClarEvalRunner(
        backend=backend,
        simulator_backend=simulator_backend,
        evaluator_backend=evaluator_backend,
        config=config,
    )


def cmd_run(args: argparse.Namespace) -> None:
    tasks = load_clareval_jsonl(args.dataset)
    backend = build_backend(args.backend, args.model, args.base_url, args.api_key)
    simulator_backend = (
        backend
        if args.simulator_model is None
        else build_backend(args.backend, args.simulator_model, args.base_url, args.api_key)
    )
    evaluator_backend = (
        simulator_backend
        if args.evaluator_model is None
        else build_backend(args.backend, args.evaluator_model, args.base_url, args.api_key)
    )
    runner = build_runner(args.runner, backend, simulator_backend, evaluator_backend, args)
    runner_label = "Direct" if args.runner == "direct" else "BED"
    run_metadata = _build_run_metadata(args)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path = Path(args.progress_file) if args.progress_file else None

    mode = "w"
    completed_ids: set[str] = set()
    if args.resume:
        completed_ids, truncated = sanitize_jsonl_for_resume(output_path)
        tasks = [t for t in tasks if t.task_id not in completed_ids]
        mode = "a"
        tqdm.write(f"Resume: {len(completed_ids)} already done, {len(tasks)} remaining.")
        if truncated:
            tqdm.write("  Truncated tail removed from output file before appending.")

    if args.max_tasks is not None:
        tasks = tasks[: args.max_tasks]

    total = len(tasks)
    if total == 0:
        print("No tasks to run.")
        return

    runner_info = (
        f"hypotheses={args.num_hypotheses}  candidates={args.num_candidates}"
        if args.runner == "bed"
        else "no hypothesis generation"
    )
    tqdm.write(
        f"\nRunner  : {runner_label}"
        f"\nDataset : {args.dataset}"
        f"\nOutput  : {args.output}"
        f"\nProgress: {args.progress_file or '(console only)'}"
        f"\nTasks   : {total}  |  concurrency={args.concurrency}"
        f"\nModels  : agent={args.model}  simulator={args.simulator_model or args.model}"
        f"  evaluator={args.evaluator_model or args.simulator_model or args.model}"
        f"\nConfig  : {runner_info}  max_turns={args.max_turns}\n"
    )

    t0 = time.time()
    write_lock = threading.Lock()
    counter = {
        "done": 0, "errors": 0,
        "completion_sum": 0.0,
        "atc_sum": 0.0, "eff_sum": 0.0,
        "sim_answered_sum": 0.0,
        "sim_answer_rate_sum": 0.0,
        "unresolved_sum": 0.0,
    }
    task_group_buckets: dict[str, dict] = {}
    for group in (
        "Ambiguous Terms / easy",
        "Missing Goal / medium",
        "Missing Premises / hard",
    ):
        task_group_buckets[group] = {
            "n": 0,
            "completion": 0.0,
            "atc": 0.0,
            "eff": 0.0,
            "sim_answered": 0.0,
            "sim_answer_rate": 0.0,
            "unresolved": 0.0,
        }

    handle = output_path.open(mode, encoding="utf-8")
    _write_progress_file(
        progress_path,
        status="running",
        counter=counter,
        task_group_buckets=task_group_buckets,
        total=total,
        started_at=t0,
        metadata=run_metadata,
    )

    pbar = tqdm(
        total=total,
        unit="task",
        ncols=90,
        desc=runner_label,
        dynamic_ncols=False,
        file=sys.stdout,
    )

    def run_one(task):
        try:
            result = runner.run_task(task)
            row = asdict(result)
            row["dialogue"] = [asdict(turn) for turn in result.dialogue]
            row["run_metadata"] = run_metadata
            blob = json.dumps(row, ensure_ascii=False, indent=2) + "\n\n"

            completion = result.metrics.get("completion_rate", 0.0)
            atc = result.metrics.get("atc", 0.0)
            eff = result.metrics.get("efficiency_ratio", 0.0)
            sim_answered = result.metrics.get("simulator_answered_count", 0.0)
            sim_answer_rate = result.metrics.get("simulator_answer_rate", 0.0)
            unresolved = 1.0 if result.metrics.get("unresolved", False) else 0.0
            task_group = f"{task.fuzzy_type} / {task.difficulty}"

            with write_lock:
                handle.write(blob)
                handle.flush()

                counter["done"] += 1
                counter["completion_sum"] += completion
                counter["atc_sum"] += atc
                counter["eff_sum"] += eff
                counter["sim_answered_sum"] += sim_answered
                counter["sim_answer_rate_sum"] += sim_answer_rate
                counter["unresolved_sum"] += unresolved

                if task_group in task_group_buckets:
                    b = task_group_buckets[task_group]
                    b["n"] += 1
                    b["completion"] += completion
                    b["atc"] += atc
                    b["eff"] += eff
                    b["sim_answered"] += sim_answered
                    b["sim_answer_rate"] += sim_answer_rate
                    b["unresolved"] += unresolved

                n = counter["done"]
                elapsed = time.time() - t0
                eta = (elapsed / n) * (total - n) if n < total else 0.0

                pbar.set_description(_fmt_summary(counter, total, elapsed))
                pbar.update(1)

                # One line per completed task
                tqdm.write(
                    f"  [{n:>3}/{total}] {task.task_id:<30}"
                    f"  completion={completion:.2f}  ATC={atc:.0f}"
                    f"  answered={sim_answered:.0f}  unresolved={bool(unresolved)}"
                    f"  elapsed={elapsed:>5.0f}s  ETA={eta:>5.0f}s"
                )

                # Periodic aggregate summary
                _write_progress_file(
                    progress_path,
                    status="running",
                    counter=counter,
                    task_group_buckets=task_group_buckets,
                    total=total,
                    started_at=t0,
                    metadata=run_metadata,
                    last_task_id=task.task_id,
                )

                if args.summary_interval and (n % args.summary_interval == 0 or n == total):
                    _print_rolling_summary(counter, task_group_buckets)

        except Exception as exc:
            with write_lock:
                counter["errors"] += 1
                pbar.update(1)
                _write_progress_file(
                    progress_path,
                    status="running",
                    counter=counter,
                    task_group_buckets=task_group_buckets,
                    total=total,
                    started_at=t0,
                    metadata=run_metadata,
                )
                tqdm.write(f"  ERROR {task.task_id}: {exc}", file=sys.stderr)

    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [executor.submit(run_one, task) for task in tasks]
            for _ in as_completed(futures):
                pass
    finally:
        pbar.close()
        handle.close()

    elapsed = time.time() - t0
    _write_progress_file(
        progress_path,
        status="finished",
        counter=counter,
        task_group_buckets=task_group_buckets,
        total=total,
        started_at=t0,
        metadata=run_metadata,
    )
    tqdm.write(
        f"\nFinished. {counter['done']} written, {counter['errors']} errors."
        f"  Total time: {elapsed:.0f}s  ({elapsed/60:.1f} min)"
    )


def cmd_evaluate(args: argparse.Namespace) -> None:
    summary = evaluate_predictions(args.predictions)
    report = format_report(summary)
    print(report)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ClarEval Experiment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run clarification on a ClarEval dataset")
    run_p.add_argument("--dataset", required=True)
    run_p.add_argument("--output", required=True)
    run_p.add_argument(
        "--runner", choices=["bed", "direct"], default="bed",
        help="bed: full BED pipeline with EIG ranking (default); "
             "direct: baseline that asks questions directly without hypothesis generation",
    )
    run_p.add_argument("--backend", choices=["mock", "openai"], default="mock")
    run_p.add_argument("--model", default="gpt-4o-mini")
    run_p.add_argument(
        "--simulator-model",
        default=None,
        help=(
            "Optional model for simulated user answers. Defaults to --model. "
            "Use a fixed value across runs for fair comparisons."
        ),
    )
    run_p.add_argument(
        "--evaluator-model",
        default=None,
        help=(
            "Optional model for final code evaluation. Defaults to --simulator-model "
            "when provided, otherwise --model."
        ),
    )
    run_p.add_argument("--base-url", default=None, help="OpenAI-compatible API base URL")
    run_p.add_argument("--api-key", default=None, help="API key")
    run_p.add_argument("--num-hypotheses", type=int, default=4)
    run_p.add_argument("--num-candidates", type=int, default=4)
    run_p.add_argument(
        "--max-turns",
        type=int,
        default=6,
        help=(
            "Maximum agent action turns. Each turn either asks one clarification "
            "question or emits the final code."
        ),
    )
    run_p.add_argument("--concurrency", type=int, default=3,
                       help="Number of tasks to run in parallel")
    run_p.add_argument("--summary-interval", type=int, default=_DEFAULT_SUMMARY_INTERVAL,
                       help="Print a rolling metric summary every N completed tasks; use 0 to disable")
    run_p.add_argument("--progress-file",
                       help="Optional JSON file updated after each completed task for external monitoring")
    run_p.add_argument("--resume", action="store_true",
                       help="Skip already-completed tasks in the output file")
    run_p.add_argument("--max-tasks", type=int,
                       help="Cap the number of tasks (useful for dry runs)")
    run_p.set_defaults(func=cmd_run)

    eval_p = subparsers.add_parser("evaluate", help="Evaluate result jsonl files")
    eval_p.add_argument("--predictions", required=True)
    eval_p.add_argument("--report", help="Optional path to write the text report")
    eval_p.set_defaults(func=cmd_evaluate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
