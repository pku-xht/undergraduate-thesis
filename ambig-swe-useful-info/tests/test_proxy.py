import json

from ambig_swe_useful_info.llm.base import LLMBackend
from ambig_swe_useful_info.proxy.prompts import PROXY_SYSTEM_PROMPT
from ambig_swe_useful_info.proxy.simulator import call_proxy


class CapturingProxyBackend(LLMBackend):
    def __init__(self):
        self.system = ""
        self.user = ""

    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        self.system = system
        self.user = user
        return json.dumps(
            {
                "selected_id": "UI1",
                "reasoning": "The question asks multiple slots; selecting the earliest directly asked item.",
            }
        )


def test_proxy_prompt_tiebreaks_multi_slot_questions_without_changing_wire_format():
    assert "If the question directly or clearly asks about multiple remaining items" in PROXY_SYSTEM_PROMPT
    assert '"selected_id": "UI1"' in PROXY_SYSTEM_PROMPT

    backend = CapturingProxyBackend()
    result = call_proxy(
        backend,
        "Could you provide the exact error message and the versions you compared?",
        [
            "The exact error message mentions the lowercased app label.",
            "The bug was observed on Django 3.1b1 and did not occur on Django 3.0.",
        ],
    )

    assert result.selected_id == "UI1"
    assert result.selected_item == "The exact error message mentions the lowercased app label."
    assert "multiple remaining items" in backend.system
