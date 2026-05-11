from ambig_swe_useful_info.data.loader import load_ambig_swe_jsonl


def test_loader_reads_one_record(sample_dataset_path):
    tasks = load_ambig_swe_jsonl(sample_dataset_path)
    assert len(tasks) == 1
    t = tasks[0]
    assert t.task_id == "astropy__astropy-12907"
    assert "FITS" in t.hidden_issue
    assert "header.py" in t.full_issue
    assert len(t.useful_info_explanations) == len(t.useful_info_items)
    assert t.useful_info_explanations[0]["bugfix_usefulness"] == "This localizes the bug."
