from ambig_swe_useful_info.bed.planner import BEDAmbigRunner
from ambig_swe_useful_info.config import BEDConfig
from ambig_swe_useful_info.data.loader import load_ambig_swe_jsonl
from ambig_swe_useful_info.direct.runner import DirectAmbigRunner
from ambig_swe_useful_info.llm.mock_backend import MockBackend


def test_bed_runner_smoke(sample_dataset_path):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    runner = BEDAmbigRunner(
        backend=MockBackend(),
        config=BEDConfig(num_hypotheses=2, num_candidates=2, max_turns=2),
    )
    events = []
    result = runner.run_task(tasks[0], progress_callback=lambda event, payload: events.append(event))
    assert result.runner == "bed"
    assert result.task_id == tasks[0].task_id
    assert len(result.asked_questions) >= 1
    assert len(result.dialogue) >= 3   # initial + at least one (agent, user) pair
    assert len(result.turn_details) == len(result.asked_questions)
    # Each turn should have hypotheses_before, candidates_ranked with EIG values
    td = result.turn_details[0]
    assert len(td.hypotheses_before) >= 1
    assert len(td.candidates_ranked) >= 1
    assert any(c.eig != 0.0 for c in td.candidates_ranked) or len(td.candidates_ranked) >= 1
    # Single-call BED planner: axes persisted + each candidate tagged with an axis
    assert len(td.disagreement_axes) >= 1
    assert all(c.axis_name != "" for c in td.candidates_ranked)
    assert td.proxy_selected_id is not None
    assert td.selected_useful_info in tasks[0].useful_info_items
    assert td.newly_covered == [td.selected_useful_info]
    assert td.coverage_ratio_after > 0.0
    assert result.metrics["stop_reason"] in {"all_useful_info_covered", "max_turns_reached"}
    # Run-time metrics are ATC + IDK only (cosine machinery removed)
    assert "atc" in result.metrics
    assert "n_idk_responses" in result.metrics
    assert isinstance(result.metrics["atc"], float)
    assert "planner_request" in events
    assert "planner_done" in events
    assert "turn_done" in events


def test_direct_runner_smoke(sample_dataset_path):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    runner = DirectAmbigRunner(
        backend=MockBackend(),
        config=BEDConfig(max_turns=2),
    )
    events = []
    result = runner.run_task(tasks[0], progress_callback=lambda event, payload: events.append(event))
    assert result.runner == "direct"
    assert len(result.turn_details) == len(result.asked_questions)
    td = result.turn_details[0]
    assert td.hypotheses_before == []
    assert td.candidates_ranked == []
    assert td.proxy_selected_id is not None
    assert td.selected_useful_info in tasks[0].useful_info_items
    assert td.coverage_ratio_after > 0.0
    assert "atc" in result.metrics
    assert "n_idk_responses" in result.metrics
    assert "stop_reason" in result.metrics
    assert "agent_request" in events
    assert "proxy_request" in events
    assert "turn_done" in events
