from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gmail Inbox API"

    # LLM (Ollama, OpenAI-compatible endpoint)
    ollama_model: str
    ollama_base_url: str
    ollama_api_key: str = "ollama"

    # Gmail OAuth
    gmail_client_secret_file: Path = Path("credentials/client_secret.json")
    gmail_token_file: Path = Path("credentials/token.json")
    gmail_scopes: list[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
    # Port the one-off OAuth consent redirect listens on (not the API port).
    # 0 lets the OS pick any free port.
    gmail_oauth_port: int = 0

    # OCR (Tesseract). Leave tesseract_cmd empty to auto-detect the install.
    tesseract_cmd: str | None = None
    ocr_languages: str = "eng"

    @property
    def client_secret_path(self) -> Path:
        return self._resolve(self.gmail_client_secret_file)

    @property
    def token_path(self) -> Path:
        return self._resolve(self.gmail_token_file)

    @staticmethod
    def _resolve(path: Path) -> Path:
        return path if path.is_absolute() else BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
