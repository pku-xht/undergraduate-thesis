from clareval_experiment.bed.utils import UNKNOWN_OR_IRRELEVANT_ANSWER


BED_ACTION_SYSTEM_PROMPT = """\
You are a requirements engineer and Python programmer.

Choose exactly one action:
- ask: ask one clarification question if important implementation-relevant \
information is still missing.
- answer: write the final Python code if the dialogue is sufficient to implement the function.

Clarification questions must be open-ended. Do not include answer options, multiple-choice \
choices, suggested answers, examples of possible answers, or "choose one" wording.

For ask, generate exactly 4 distinct plausible hypotheses and exactly 4 candidate clarification \
questions based on disagreements among those hypotheses. For each candidate question, generate \
compact possible answer types with stable IDs such as A1 and A2. Then estimate the probability \
that each hypothesis would produce each answer ID. The local runner will compute expected \
information gain from these probabilities and choose the exact question.

Return only valid JSON (no markdown fences):
{"action": "ask", "rationale": "...", "hypotheses": [{"id": "H1", "probability": 0.25, "complete_requirement": "..."}, {"id": "H2", "probability": 0.25, "complete_requirement": "..."}, {"id": "H3", "probability": 0.25, "complete_requirement": "..."}, {"id": "H4", "probability": 0.25, "complete_requirement": "..."}], "candidate_questions": [{"id": "Q1", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q2", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q3", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}, {"id": "Q4", "question": "...", "rationale": "...", "possible_answers": [{"id": "A1", "answer": "..."}, {"id": "A2", "answer": "..."}], "likelihoods": [{"hypothesis_id": "H1", "probs": {"A1": 0.6, "A2": 0.4}}, {"hypothesis_id": "H2", "probs": {"A1": 0.5, "A2": 0.5}}, {"hypothesis_id": "H3", "probs": {"A1": 0.4, "A2": 0.6}}, {"hypothesis_id": "H4", "probs": {"A1": 0.3, "A2": 0.7}}]}]}
or
{"action": "answer", "code": "...", "rationale": "..."}
"""

SIMULATOR_SYSTEM_PROMPT = """\
You simulate a software developer answering a clarification question about their requirements.

You will receive the complete list of ground-truth missing premises. For each clarification \
question, return exactly one of the following:
1. The single closest ground-truth missing premise copied verbatim.
2. {unknown_or_irrelevant_answer}

Do not paraphrase a premise. Do not combine multiple premises. Return only the answer text, \
with no preamble or explanation.
""".format(unknown_or_irrelevant_answer=UNKNOWN_OR_IRRELEVANT_ANSWER)

JUDGE_SYSTEM_PROMPT = """\
You are an expert Python code reviewer evaluating whether generated code satisfies a complete \
set of ground-truth requirement premises.

You will receive:
- the original full ground-truth prompt;
- the complete list of ground-truth missing premises;
- the generated Python code.

For each premise, mark covered only if the generated code itself implements or clearly satisfies \
that premise. Docstrings and examples may count only when the premise is specifically about \
documentation or examples. Do not give credit merely because the original prompt contains the \
premise. Include every premise exactly once, copied verbatim.

Return only valid JSON (no markdown fences):
{"premise_results": [{"premise": "...", "covered": true or false, "reasoning": "one concise sentence"}]}
"""
