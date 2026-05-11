"""Run ReqElicitGym interviewer experiments with LLM interviewer/evaluator calls."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from reqelicitgym_experiment.interviewers import build_interviewer
from reqelicitgym_experiment.llm_client import LLMClient
from reqelicitgym_experiment.llm_gym import LLMReqElicitEpisode, aggregate_metrics, load_tasks


ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "ReqElicitGym_10.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
DEFAULT_MODELS = ["ds/deepseek-v4-flash", "ds/deepseek-v4-pro"]
DEFAULT_JUDGE_MODEL = "ds/deepseek-v4-pro"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def model_suffix(model: str) -> str:
    """Create a readable output suffix for known DeepSeek model names."""
    if model.endswith("v4-flash"):
        return "flash"
    if model.endswith("v4-pro"):
        return "pro"
    return (
        model.rsplit("/", 1)[-1]
        .replace("-", "_")
        .replace(".", "_")
        .replace(":", "_")
    )


def run_method(
    method: str,
    tasks: List[Dict[str, Any]],
    llm: LLMClient,
    *,
    output_path: Optional[Path] = None,
    num_hypotheses: int = 4,
    num_candidates: int = 4,
    resume: bool = False,
    evaluator_llm: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    task_results = []
    conversations = []
    start_index = 0
    if resume and output_path is not None and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("method") == method:
            task_results = existing.get("task_results", [])
            conversations = existing.get("conversations", [])
            start_index = len(task_results)

    total_tasks = len(tasks)
    print(
        f"[{method}] starting {total_tasks - start_index}/{total_tasks} tasks "
        "(step budget = hidden requirement count per task)",
        flush=True,
    )
    for task_index, task in enumerate(tasks[start_index:], start=start_index):
        task_name = task.get("name", "")
        app_type = task.get("application_type", "Unknown")
        step_budget = len(task.get("Implicit Requirements", []))
        print(
            f"[{method}] task {task_index + 1}/{total_tasks}: {task_name} "
            f"({app_type}, step_budget={step_budget})",
            flush=True,
        )
        interviewer = build_interviewer(
            method,
            llm,
            max_questions=step_budget,
            num_hypotheses=num_hypotheses,
            num_candidates=num_candidates,
        )
        episode = LLMReqElicitEpisode(
            task,
            llm=llm,
            step_budget=step_budget,
            judge_llm=evaluator_llm,
        )
        done = False
        turn = 0
        while not done:
            turn += 1
            print(
                f"[{method}] task {task_index + 1}/{total_tasks} turn {turn}: "
                "generating question",
                flush=True,
            )
            question, decision_trace = interviewer.ask_question(episode.observation())
            if decision_trace.get("finish"):
                episode.finish(decision_trace)
                print(
                    f"[{method}] task {task_index + 1}/{total_tasks} turn {turn}: "
                    f"finish ({decision_trace.get('finish_reason', 'requested')})",
                    flush=True,
                )
                break
            print(
                f"[{method}] task {task_index + 1}/{total_tasks} turn {turn}: "
                f"asking {question}",
                flush=True,
            )
            _, _, done = episode.step(question, decision_trace=decision_trace)

        metrics = episode.metrics()
        metrics["task_index"] = task_index
        metrics["step_budget"] = step_budget
        task_results.append(metrics)
        conversations.append(
            {
                "task_index": task_index,
                "task_name": task.get("name", ""),
                "initial_requirements": task.get("initial_requirements", ""),
                "implicit_requirements_for_audit": task.get("Implicit Requirements", []),
                "conversation": metrics["turns"],
            }
        )
        if output_path is not None:
            partial = {
                "method": method,
                "overall": aggregate_metrics(task_results),
                "task_results": task_results,
                "conversations": conversations,
                "partial": len(task_results) < len(tasks),
            }
            output_path.write_text(json.dumps(partial, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[{method}] task {task_index + 1}/{total_tasks} done: "
            f"elicited={metrics['total_elicited']}/{metrics['total_requirements']} "
            f"rounds={metrics['num_rounds']}",
            flush=True,
        )

    return {
        "method": method,
        "overall": aggregate_metrics(task_results),
        "task_results": task_results,
        "conversations": conversations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ReqElicitGym interviewer experiments with LLM calls.")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["direct", "bed", "aspect_aware"],
        choices=["direct", "bed", "aspect_aware"],
    )
    parser.add_argument("--max-tasks", type=int, default=10)
    parser.add_argument("--num-hypotheses", type=int, default=4)
    parser.add_argument("--num-candidates", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument(
        "--models",
        nargs="+",
        default=os.environ.get("OPENAI_MODELS", "").split() or DEFAULT_MODELS,
    )
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--summary-name", default="llm_summary.json")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main() -> None:
    load_env_file(ROOT / ".env")
    args = build_parser().parse_args()
    if not args.api_key:
        raise SystemExit("Missing API key. Pass --api-key or set OPENAI_API_KEY.")
    if not args.base_url:
        raise SystemExit("Missing base URL. Pass --base-url or set OPENAI_BASE_URL.")

    tasks = load_tasks(args.data_path, limit=args.max_tasks)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    evaluator_llm = LLMClient(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.judge_model,
        temperature=0.0,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )

    all_results = {}
    for model in args.models:
        llm = LLMClient(
            api_key=args.api_key,
            base_url=args.base_url,
            model=model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        suffix = model_suffix(model)
        for method in args.methods:
            run_id = f"{method}_{suffix}"
            output_path = args.output_dir / f"{run_id}_results.json"
            result = run_method(
                method,
                tasks,
                llm,
                output_path=output_path,
                num_hypotheses=args.num_hypotheses,
                num_candidates=args.num_candidates,
                resume=args.resume,
                evaluator_llm=evaluator_llm,
            )
            result["interviewer_model"] = model
            result["evaluator_model"] = args.judge_model
            all_results[run_id] = result
            output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_path = args.output_dir / args.summary_name
    summary = {
        "data_path": str(args.data_path),
        "max_tasks": args.max_tasks,
        "step_budget_policy": "per_task_hidden_requirement_count",
        "num_hypotheses": args.num_hypotheses,
        "num_candidates": args.num_candidates,
        "resume": args.resume,
        "task_names": [task.get("name", "") for task in tasks],
        "application_types": [task.get("application_type", "") for task in tasks],
        "models": args.models,
        "evaluator_model": args.judge_model,
        "base_url": args.base_url,
        "runs": {
            run_id: {
                "method": result["method"],
                "interviewer_model": result["interviewer_model"],
                "evaluator_model": result["evaluator_model"],
                "overall": result["overall"],
            }
            for run_id, result in all_results.items()
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
