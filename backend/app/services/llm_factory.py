"""
LLM Factory — creates LangChain chat model based on configured provider.

Priority order: gemini → groq → openai
Falls back automatically if primary provider fails to initialize.
"""

from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.config import settings
from app.core.exceptions import LLMException


def _create_gemini() -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.7,
        convert_system_message_to_human=False,
    )


def _create_groq() -> BaseChatModel:
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=settings.GROQ_MODEL,
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0.7,
    )


def _create_openai() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.7,
    )


_PROVIDER_MAP = {
    "gemini": _create_gemini,
    "groq": _create_groq,
    "openai": _create_openai,
}

# Fallback chain
_FALLBACK_ORDER = ["gemini", "groq", "openai"]


def get_llm(provider: str | None = None) -> BaseChatModel:
    """
    Get a LangChain chat model for the configured provider.
    Tries fallback providers if primary fails.
    """
    providers_to_try = []
    primary = provider or settings.LLM_PROVIDER

    # Primary first, then fallbacks in order
    providers_to_try.append(primary)
    for p in _FALLBACK_ORDER:
        if p != primary:
            providers_to_try.append(p)

    last_error: Exception | None = None
    for p in providers_to_try:
        creator = _PROVIDER_MAP.get(p)
        if not creator:
            continue
        try:
            # Skip provider if its API key is not configured
            if p == "gemini" and not settings.GEMINI_API_KEY:
                continue
            if p == "groq" and not settings.GROQ_API_KEY:
                continue
            if p == "openai" and not settings.OPENAI_API_KEY:
                continue
            return creator()
        except Exception as e:
            last_error = e
            continue

    raise LLMException(
        f"Failed to initialize any LLM provider. Last error: {last_error}"
    )


def get_structured_llm(schema: type, provider: str | None = None) -> Any:
    """Get a LLM that returns structured output matching the given Pydantic schema."""
    llm = get_llm(provider)
    return llm.with_structured_output(schema)
