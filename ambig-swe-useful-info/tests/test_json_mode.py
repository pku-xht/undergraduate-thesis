from ambig_swe_useful_info.bed.prompts import BED_PLANNER_SYSTEM_PROMPT
from ambig_swe_useful_info.direct.prompts import DIRECT_QUESTION_SYSTEM_PROMPT
from ambig_swe_useful_info.eval.useful_info import EXTRACT_SYSTEM_PROMPT
from ambig_swe_useful_info.llm.openai_backend import _uses_json_mode
from ambig_swe_useful_info.proxy.prompts import PROXY_SYSTEM_PROMPT


def test_json_output_prompts_enable_json_mode():
    for prompt in [
        BED_PLANNER_SYSTEM_PROMPT,
        DIRECT_QUESTION_SYSTEM_PROMPT,
        EXTRACT_SYSTEM_PROMPT,
        PROXY_SYSTEM_PROMPT,
    ]:
        assert _uses_json_mode(prompt)


def test_no_json_prompt_sample_does_not_enable_json_mode():
    assert not _uses_json_mode("Respond in natural language.")
