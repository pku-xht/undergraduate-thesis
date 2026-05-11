from __future__ import annotations

from dataclasses import dataclass

from ambig_swe_useful_info.bed.utils import safe_json_loads
from ambig_swe_useful_info.llm.base import LLMBackend
from ambig_swe_useful_info.proxy.prompts import PROXY_SYSTEM_PROMPT, PROXY_USER_TEMPLATE

IDK_RESPONSE = "I don't have that information."
PROXY_TEMPERATURE = 0.0


@dataclass
class ProxyResult:
    answer: str
    selected_id: str | None
    reasoning: str
    selected_item: str
    remaining_items_before: list[str]


def call_proxy(
    backend: LLMBackend,
    question: str,
    remaining_items: list[str],
    temperature: float = PROXY_TEMPERATURE,
) -> ProxyResult:
    if not remaining_items:
        return ProxyResult(
            answer=IDK_RESPONSE,
            selected_id=None,
            reasoning="No remaining useful-information items.",
            selected_item="",
            remaining_items_before=[],
        )

    id_to_item = {f"UI{idx + 1}": item for idx, item in enumerate(remaining_items)}
    remaining_text = "\n".join(f"{uid}: {item}" for uid, item in id_to_item.items())
    user = PROXY_USER_TEMPLATE.format(
        question=question,
        remaining_items=remaining_text,
    )
    payload = safe_json_loads(
        backend.complete(PROXY_SYSTEM_PROMPT, user, temperature=temperature),
        {"selected_id": None},
    )
    selected_id = str(payload.get("selected_id") or "").strip()
    selected_item = id_to_item.get(selected_id, "")
    return ProxyResult(
        answer=selected_item or IDK_RESPONSE,
        selected_id=selected_id or None,
        reasoning=str(payload.get("reasoning", "")).strip(),
        selected_item=selected_item,
        remaining_items_before=list(remaining_items),
    )

