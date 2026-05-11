from __future__ import annotations

from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, temperature: float = 0.2) -> str:
        raise NotImplementedError

