"""AIProvider abstraction. Providers only rephrase supplied evidence; citations are validated."""
import re
from abc import ABC, abstractmethod

from .config import Settings
from .http_util import http_json

SYSTEM = ("You are EngBrain. Answer ONLY from the EVIDENCE. Cite record ids in [brackets]. Mark anything not directly "
          "stated as 'Inference:'. If the evidence does not answer the question, reply exactly: I don't have enough "
          "historical evidence to determine this. Never invent incidents, PRs, commits, decisions or dates.")


class AIProvider(ABC):
    @abstractmethod
    def summarize(self, question: str, evidence: list[dict]) -> str | None: ...


class MockProvider(AIProvider):
    def summarize(self, question, evidence): return None


class OpenAIProvider(AIProvider):
    def __init__(self, key: str, model: str, base_url: str):
        self.key, self.model, self.base = key, model, base_url.rstrip("/")

    def summarize(self, question, evidence):
        ctx = "\n".join(f'[{e["id"]}] {e["date"]} {e["type"]}: {e["title"]}. {e["text"]}' for e in evidence)
        res = http_json("POST", f"{self.base}/chat/completions", {"Authorization": f"Bearer {self.key}"}, {
            "model": self.model, "temperature": 0.1,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"Question: {question}\n\nEVIDENCE:\n{ctx}"}]})
        return (res["choices"][0]["message"]["content"] or "").strip()


class GeminiProvider(AIProvider):
    def __init__(self, key: str, model: str, base_url: str):
        self.key, self.model, self.base = key, model, base_url.rstrip("/")

    def summarize(self, question, evidence):
        ctx = "\n".join(f'[{e["id"]}] {e["date"]} {e["type"]}: {e["title"]}. {e["text"]}' for e in evidence)
        res = http_json("POST", f"{self.base}/models/{self.model}:generateContent?key={self.key}",
                        {"Content-Type": "application/json"}, {
                            "systemInstruction": {"parts": [{"text": SYSTEM}]},
                            "contents": [{"role": "user", "parts": [{
                                "text": f"Question: {question}\n\nEVIDENCE:\n{ctx}"
                            }]}],
                            "generationConfig": {"temperature": 0.1},
                        })
        return (res["candidates"][0]["content"]["parts"][0]["text"] or "").strip()


def unknown_citations(text: str, evidence: list[dict]) -> list[str]:
    known = {e["id"] for e in evidence}
    return [i for i in re.findall(r"\[([^\]]+)\]", text) if i not in known]


def make_provider(cfg: Settings) -> AIProvider:
    if cfg.llm_provider == "gemini" and cfg.llm_api_key:
        return GeminiProvider(cfg.llm_api_key, cfg.llm_model, cfg.llm_base_url)
    if cfg.llm_provider == "openai" and cfg.llm_api_key:
        return OpenAIProvider(cfg.llm_api_key, cfg.llm_model, cfg.llm_base_url)
    return MockProvider()
