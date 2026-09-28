import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    github_token: str
    github_webhook_secret: str
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str
    hindsight_url: str
    hindsight_api_key: str
    hindsight_bank: str
    db_path: str


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    _load_dotenv(root / ".env")
    e = os.environ.get
    return Settings(
        github_token=e("GITHUB_TOKEN", ""),
        github_webhook_secret=e("GITHUB_WEBHOOK_SECRET", ""),
        llm_provider=e("LLM_PROVIDER", "gemini" if e("LLM_API_KEY") else "mock"),
        llm_api_key=e("GEMINI_API_KEY", e("LLM_API_KEY", "")),
        llm_model=e("LLM_MODEL", "gemini-2.5-flash"),
        llm_base_url=e("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        hindsight_url=e("HINDSIGHT_URL", ""),
        hindsight_api_key=e("HINDSIGHT_API_KEY", ""),
        hindsight_bank=e("HINDSIGHT_BANK", "engbrain"),
        db_path=e("ENGBRAIN_DB", str(root / "data" / "engbrain.db")),
    )
