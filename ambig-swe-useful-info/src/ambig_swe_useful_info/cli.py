from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from tqdm import tqdm

from ambig_swe_useful_info.bed.planner import BEDAmbigRunner
from ambig_swe_useful_info.config import BEDConfig
from ambig_swe_useful_info.data.loader import load_ambig_swe_jsonl
from ambig_swe_useful_info.direct.runner import DirectAmbigRunner
from ambig_swe_useful_info.eval.useful_info import extract_useful_extra_info_full
from ambig_swe_useful_info.eval.metrics import evaluate, format_report
from ambig_swe_useful_info.llm.mock_backend import MockBackend


def _occurrence_key(task_id: str, occurrence: int) -> tuple[str, int]:
    return task_id, occurrence


def _task_occurrence_pairs(tasks):
    counts: dict[str, int] = {}
    pairs = []
    for task in tasks:
        counts[task.task_id] = counts.get(task.task_id, 0) + 1
        pairs.append((_occurrence_key(task.task_id, counts[task.task_id]), task))
    return pairs


def _build_chat_backend(
    name: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    timeout: float | None = None,
):
    if name == "openai":
        from ambig_swe_useful_info.llm.openai_backend import OpenAIBackend
        return OpenAIBackend(model, base_url=base_url, api_key=api_key, timeout=timeout)
    return MockBackend()


def _build_runner(runner_name: str, backend, proxy_backend, args: argparse.Namespace):
    config = BEDConfig(
        num_hypotheses=args.num_hypotheses,
        num_candidates=args.num_candidates,
        max_turns=args.max_turns,
    )
    if runner_name == "direct":
        return DirectAmbigRunner(
            backend=backend,
            config=config,
            proxy_backend=proxy_backend,
        )
    return BEDAmbigRunner(
        backend=backend,
        config=config,
        proxy_backend=proxy_backend,
    )


def _sanitize_jsonl_for_resume(path: Path) -> tuple[set[tuple[str, int]], bool]:
    completed: set[tuple[str, int]] = set()
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
            if isinstance(obj, dict):
                valid_records.append(obj)
            else:
                truncated = True
                break
        except json.JSONDecodeError:
            truncated = True
            break
    counts: dict[str, int] = {}
    for row in valid_records:
        tid = row.get("task_id")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
            completed.add(_occurrence_key(tid, counts[tid]))
    if truncated:
        with path.open("w", encoding="utf-8") as handle:
            for row in valid_records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return completed, truncated


def _format_turn_progress(event: str, payload: dict) -> str:
    runner = str(payload.get("runner", "")).upper()
    turn = payload.get("turn", "?")
    prefix = f"    {runner} turn {turn}:"
    if event == "turn_start":
        return (
            f"{prefix} start "
            f"covered={payload.get('covered', 0)}/{payload.get('total', 0)}"
        )
    if event == "agent_request":
        return f"{prefix} requesting next question"
    if event == "planner_request":
        return f"{prefix} requesting BED plan"
    if event == "planner_done":
        return (
            f"{prefix} planner returned "
            f"hypotheses={payload.get('hypotheses', 0)} "
            f"candidates={payload.get('candidates', 0)} "
            f"fallback={payload.get('used_fallback', False)}"
        )
    if event == "agent_question":
        eig = payload.get("eig")
        eig_part = f" eig={float(eig):.4f}" if isinstance(eig, (int, float)) else ""
        question = str(payload.get("question", "")).replace("\n", " ")
        return f"{prefix} selected question{eig_part}: {question}"
    if event == "proxy_request":
        return f"{prefix} querying proxy remaining={payload.get('remaining', 0)}"
    if event == "turn_done":
        stop = payload.get("stop_reason") or ""
        stop_part = f" stop={stop}" if stop else ""
        return (
            f"{prefix} done selected={payload.get('selected_id') or 'IDK'} "
            f"new={payload.get('newly_covered', 0)} "
            f"covered={payload.get('covered', 0)}/{payload.get('total', 0)} "
            f"ratio={float(payload.get('coverage_ratio', 0.0)):.3f}"
            f"{stop_part}"
        )
    if event == "no_question":
        return f"{prefix} no question stop={payload.get('stop_reason')}"
    return f"{prefix} {event} {payload}"


def cmd_run(args: argparse.Namespace) -> None:
    tasks = load_ambig_swe_jsonl(args.dataset)
    task_pairs = _task_occurrence_pairs(tasks)

    backend = _build_chat_backend(
        args.backend, args.model, args.base_url, args.api_key, args.request_timeout
    )
    proxy_backend = _build_chat_backend(
        args.backend, args.proxy_model, args.base_url, args.api_key, args.request_timeout
    )
    runner = _build_runner(args.runner, backend, proxy_backend, args)
    runner_label = "Direct" if args.runner == "direct" else "BED"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "w"
    completed_ids: set[tuple[str, int]] = set()
    if args.resume:
        completed_ids, truncated = _sanitize_jsonl_for_resume(output_path)
        task_pairs = [(key, t) for key, t in task_pairs if key not in completed_ids]
        mode = "a"
        tqdm.write(f"Resume: {len(completed_ids)} already done, {len(task_pairs)} remaining.")
        if truncated:
            tqdm.write("  Truncated tail removed from output file before appending.")
    elif output_path.exists():
        tqdm.write(f"Overwrite: truncating existing output file {output_path}")

    if args.max_tasks is not None:
        task_pairs = task_pairs[: args.max_tasks]

    total = len(task_pairs)
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
        f"\nTasks   : {total}"
        f"\nModels  : agent={args.model}  proxy={args.proxy_model}"
        f"\nConfig  : {runner_info}  max_turns={args.max_turns}"
        "\n"
    )

    t0 = time.time()
    counter = {"done": 0, "errors": 0, "atc_sum": 0.0, "idk_sum": 0.0}

    handle = output_path.open(mode, encoding="utf-8")
    pbar = tqdm(total=total, unit="task", ncols=90, desc=runner_label, file=sys.stdout)

    def run_one(row_key, task) -> None:
        try:
            def progress(event: str, payload: dict) -> None:
                tqdm.write(_format_turn_progress(event, payload))

            result = runner.run_task(
                task,
                progress_callback=progress if args.verbose_turns else None,
            )
            row = asdict(result)
            row["dialogue"] = [asdict(turn) for turn in result.dialogue]
            row["metadata"].update(
                {
                    "dataset": args.dataset,
                    "row_occurrence": row_key[1],
                    "agent_model": args.model,
                    "proxy_model": args.proxy_model,
                    "backend": args.backend,
                    "runner": args.runner,
                    "output": args.output,
                    "request_timeout": args.request_timeout,
                }
            )
            blob = json.dumps(row, ensure_ascii=False) + "\n"

            atc = result.metrics.get("atc", 0.0)
            idk = result.metrics.get("n_idk_responses", 0)

            handle.write(blob)
            handle.flush()
            counter["done"] += 1
            counter["atc_sum"] += atc
            counter["idk_sum"] += idk

            n = counter["done"]
            elapsed = time.time() - t0
            eta = (elapsed / n) * (total - n) if n < total else 0.0

            pbar.set_description(
                f"{runner_label} atc={counter['atc_sum']/n:.2f} idk={counter['idk_sum']/n:.2f}"
            )
            pbar.update(1)

            tqdm.write(
                f"  [{n:>3}/{total}] {task.task_id:<30}"
                f"  atc={atc:.0f}  idk={idk}"
                f"  elapsed={elapsed:>5.0f}s  ETA={eta:>5.0f}s"
            )
        except Exception as exc:
            counter["errors"] += 1
            pbar.update(1)
            tqdm.write(f"  ERROR {task.task_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    try:
        for row_key, task in task_pairs:
            run_one(row_key, task)
    finally:
        pbar.close()
        handle.close()

    elapsed = time.time() - t0
    tqdm.write(
        f"\nFinished. {counter['done']} written, {counter['errors']} errors."
        f"  Total time: {elapsed:.0f}s  ({elapsed/60:.1f} min)"
    )
    if counter["errors"]:
        raise SystemExit(1)


def cmd_evaluate(args: argparse.Namespace) -> None:
    summary = evaluate(
        bed_path=args.bed,
        direct_path=args.direct,
        dataset_path=args.dataset,
        max_tasks=args.max_tasks,
        max_turns=args.max_turns,
    )

    report = format_report(summary)
    print(report)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")

    if args.per_task_jsonl:
        per_path = Path(args.per_task_jsonl)
        per_path.parent.mkdir(parents=True, exist_ok=True)
        with per_path.open("w", encoding="utf-8") as h:
            for row in summary["per_task"]:
                h.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_prepare_useful_info(args: argparse.Namespace) -> None:
    backend = _build_chat_backend(
        args.backend, args.model, args.base_url, args.api_key, args.request_timeout
    )
    rows = [
        json.loads(line)
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.max_tasks is not None:
        rows = rows[: args.max_tasks]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        pbar = tqdm(total=len(rows), unit="task", ncols=90, desc="Useful info", file=sys.stdout)
        for row in rows:
            payload = extract_useful_extra_info_full(
                backend=backend,
                full_issue=row.get("full_issue", ""),
                hidden_issue=row.get("hidden_issue", ""),
                temperature=0.0,
            )
            out = dict(row)
            out["useful_info_items"] = payload["items"]
            out["useful_info_explanations"] = payload["explanations"]
            out["useful_info_sufficiency"] = payload["sufficiency"]
            handle.write(json.dumps(out, ensure_ascii=False) + "\n")
            handle.flush()
            pbar.update(1)
            tqdm.write(
                f"  [{pbar.n:>3}/{len(rows)}] {row.get('task_id', ''):<30}"
                f"  useful_items={len(payload['items'])}"
            )
        pbar.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ambig-SWE useful-info recovery CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run clarification on an Ambig-SWE dataset")
    run_p.add_argument("--dataset", required=True)
    run_p.add_argument("--output", required=True)
    run_p.add_argument("--runner", choices=["bed", "direct"], default="bed")
    run_p.add_argument("--backend", choices=["mock", "openai"], default="mock")
    run_p.add_argument("--model", default="ds/deepseek-v4-flash")
    run_p.add_argument("--proxy-model", default="ds/deepseek-v4-pro")
    run_p.add_argument("--base-url", default=None)
    run_p.add_argument("--api-key", default=None)
    run_p.add_argument("--request-timeout", type=float, default=None,
                       help="Per-request timeout in seconds for OpenAI-compatible calls; default 600.")
    run_p.add_argument("--num-hypotheses", type=int, default=4)
    run_p.add_argument("--num-candidates", type=int, default=4)
    run_p.add_argument("--max-turns", type=int, default=5)
    run_p.add_argument("--verbose-turns", action="store_true",
                       help="Print turn-level progress within each task.")
    run_p.add_argument("--resume", action="store_true")
    run_p.add_argument("--max-tasks", type=int)
    run_p.set_defaults(func=cmd_run)

    eval_p = subparsers.add_parser("evaluate", help="Coverage + TTR report over useful issue info")
    eval_p.add_argument("--bed", required=True)
    eval_p.add_argument("--direct", required=True)
    eval_p.add_argument("--dataset", required=True)
    eval_p.add_argument("--report")
    eval_p.add_argument("--per-task-jsonl")
    eval_p.add_argument("--max-tasks", type=int)
    eval_p.add_argument("--max-turns", type=int, default=5,
                        help="Upper bound used by TTR + per-turn coverage; censored TTR = max_turns + 1")
    eval_p.set_defaults(func=cmd_evaluate)

    prep_p = subparsers.add_parser(
        "prepare-useful-info",
        help="Create a clean dataset annotated with useful-info targets",
    )
    prep_p.add_argument("--input", default="ambig_swe_10_clean.jsonl")
    prep_p.add_argument("--output", default="ambig_swe_10_clean_with_useful_info.jsonl")
    prep_p.add_argument("--backend", choices=["mock", "openai"], default="openai")
    prep_p.add_argument("--model", default="ds/deepseek-v4-pro")
    prep_p.add_argument("--base-url", default=None)
    prep_p.add_argument("--api-key", default=None)
    prep_p.add_argument("--request-timeout", type=float, default=None,
                        help="Per-request timeout in seconds for OpenAI-compatible calls; default 600.")
    prep_p.add_argument("--max-tasks", type=int)
    prep_p.set_defaults(func=cmd_prepare_useful_info)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

