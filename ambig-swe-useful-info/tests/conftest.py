import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_record() -> dict:
    return {
        "task_id": "astropy__astropy-12907",
        "repo": "astropy/astropy",
        "hidden_issue": "FITS keyword validation is wrong; please fix it.",
        "full_issue": (
            "When writing a FITS header in astropy/io/fits/header.py, an overlong "
            "keyword silently truncates instead of raising a clear ValueError."
        ),
        "useful_info_items": [
            "The affected file is astropy/io/fits/header.py.",
            "The expected behavior is to raise a clearer ValueError for overlong FITS keywords.",
        ],
        "useful_info_explanations": [
            {
                "category": "scope",
                "source_evidence": "astropy/io/fits/header.py",
                "hidden_issue_gap": "The shortened issue omits the affected file.",
                "bugfix_usefulness": "This localizes the bug.",
                "ordinary_reporter_answerability": "The reporter can mention the file they were editing.",
                "abstraction_note": "The concrete file path is load-bearing in this test fixture.",
            },
            {
                "category": "expected_behavior",
                "source_evidence": "raising a clear ValueError",
                "hidden_issue_gap": "The shortened issue omits the expected failure behavior.",
                "bugfix_usefulness": "This states the intended failure behavior.",
                "ordinary_reporter_answerability": "The reporter can describe the expected error.",
                "abstraction_note": "The expected behavior is already atomic.",
            },
        ],
        "useful_info_sufficiency": "The private context identifies the affected file and expected validation behavior.",
    }


@pytest.fixture
def sample_dataset_path(tmp_path: Path, sample_record: dict) -> Path:
    p = tmp_path / "ambig_swe_10_clean.jsonl"
    p.write_text(json.dumps(sample_record) + "\n", encoding="utf-8")
    return p
