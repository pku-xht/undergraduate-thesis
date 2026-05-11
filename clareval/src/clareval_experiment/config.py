from dataclasses import dataclass


@dataclass
class BEDConfig:
    num_hypotheses: int = 4
    num_candidates: int = 4
    # Maximum agent action turns. Each turn either asks one clarification
    # question or emits the final code.
    max_turns: int = 6
    temperature: float = 0.2
