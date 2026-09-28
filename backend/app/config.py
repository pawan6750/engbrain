import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _groq_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/") or "https://api.groq.com/openai/v1"
    parts = urlsplit(base_url)
    if (parts.hostname or "").lower() == "api.groq.com":
        path = parts.path.rstrip("/")
        if path.endswith("/chat/completions"):
            path = path[:-len("/chat/completions")]
        if not path.endswith("/openai/v1"):
            path = f"{path}/openai/v1".replace("//", "/")
        base_url = urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return base_url.rstrip("/")


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
    provider = e("LLM_PROVIDER", "").strip().lower()
    groq_key = e("GROQ_API_KEY", "").strip()
    generic_key = e("LLM_API_KEY", "").strip()
    gemini_key = e("GEMINI_API_KEY", "").strip()
    if not provider:
        provider = "groq" if groq_key else "gemini" if gemini_key or generic_key else "mock"
    if provider == "groq":
        api_key = groq_key or generic_key
    elif provider == "gemini":
        api_key = gemini_key or generic_key
    else:
        api_key = generic_key or groq_key or gemini_key
    model = e("LLM_MODEL", "").strip()
    if not model:
        model = "llama-3.3-70b-versatile" if provider == "groq" else "gemini-2.5-flash"
    base_url = e("LLM_BASE_URL", "").strip()
    if provider == "groq" or "api.groq.com" in base_url.lower():
        base_url = _groq_base_url(base_url)
    elif not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta"
    return Settings(
        github_token=e("GITHUB_TOKEN", ""),
        github_webhook_secret=e("GITHUB_WEBHOOK_SECRET", ""),
        llm_provider=provider,
        llm_api_key=api_key,
        llm_model=model,
        llm_base_url=base_url,
        hindsight_url=e("HINDSIGHT_URL", ""),
        hindsight_api_key=e("HINDSIGHT_API_KEY", ""),
        hindsight_bank=e("HINDSIGHT_BANK", "engbrain"),
        db_path=e("ENGBRAIN_DB", str(root / "data" / "engbrain.db")),
    )
