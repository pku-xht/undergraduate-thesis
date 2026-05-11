from dataclasses import dataclass


@dataclass
class BEDConfig:
    num_hypotheses: int = 4
    num_candidates: int = 4
    max_turns: int = 5
    temperature: float = 0.2
    top_p: float = 0.95

