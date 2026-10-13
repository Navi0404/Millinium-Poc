from functools import lru_cache

from app.core.config import get_settings
from app.services.gmail_service import GmailService
from app.services.llm_service import LLMService


@lru_cache
def get_gmail_service() -> GmailService:
    return GmailService(get_settings())


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService(get_settings())
