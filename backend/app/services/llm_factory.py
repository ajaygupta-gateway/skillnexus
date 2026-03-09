"""
LLM Factory — creates LangChain chat model based on configured provider.

Priority order: configured primary → remaining providers in order (gemini → groq → openai).

Runtime fallback: if the primary provider raises ANY exception during an actual
model call (rate-limit, quota exceeded, timeout, network error), LangChain's
built-in .with_fallbacks() silently retries the next available provider.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.config import settings
from app.core.exceptions import LLMException


# ── Provider constructors ──────────────────────────────────────────────────────

def _create_gemini() -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.7,
        max_tokens=3000,
        convert_system_message_to_human=False,
    )


def _create_groq() -> BaseChatModel:
    from langchain_groq import ChatGroq
    return ChatGroq(
        model=settings.GROQ_MODEL,
        groq_api_key=settings.GROQ_API_KEY,
        temperature=0.7,
        max_tokens=3000,
    )


def _create_openai() -> BaseChatModel:
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.7,
        max_tokens=3000,
    )


_PROVIDER_CREATORS = {
    "gemini": (_create_gemini, lambda: bool(settings.GEMINI_API_KEY)),
    "groq":   (_create_groq,   lambda: bool(settings.GROQ_API_KEY)),
    "openai": (_create_openai, lambda: bool(settings.OPENAI_API_KEY)),
}

# Fixed fallback order (primary is moved to front at runtime)
_FALLBACK_ORDER = ["gemini", "groq", "openai"]


def _build_provider_chain(primary: str) -> list[str]:
    """Return [primary, ...rest] with only providers that have an API key configured."""
    order = [primary] + [p for p in _FALLBACK_ORDER if p != primary]
    return [p for p in order if _PROVIDER_CREATORS[p][1]()]   # filter by key check


def _instantiate(provider: str) -> BaseChatModel:
    creator, _ = _PROVIDER_CREATORS[provider]
    try:
        return creator()
    except Exception as e:
        raise LLMException(f"Failed to initialise {provider}: {e}") from e


# ── Public API ─────────────────────────────────────────────────────────────────

def get_llm(provider: str | None = None) -> BaseChatModel:
    """
    Return a LangChain chat model with RUNTIME fallback support.

    If the primary provider raises an exception during an actual model call
    (e.g. 429 rate-limit, timeout, quota exceeded), LangChain automatically
    retries the next configured provider — completely transparently.
    """
    chain = _build_provider_chain(provider or settings.LLM_PROVIDER)
    if not chain:
        raise LLMException(
            "No LLM provider is configured. Set at least one of "
            "GEMINI_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY."
        )

    primary_llm = _instantiate(chain[0])

    if len(chain) == 1:
        return primary_llm

    # Build fallback instances (skip any that fail to instantiate too)
    fallbacks: list[BaseChatModel] = []
    for p in chain[1:]:
        try:
            fallbacks.append(_instantiate(p))
        except LLMException:
            continue   # just skip broken providers in the fallback list

    if not fallbacks:
        return primary_llm

    # LangChain's .with_fallbacks() retries on ANY exception during invocation
    return primary_llm.with_fallbacks(fallbacks)


def get_structured_llm(schema: type, provider: str | None = None) -> Any:
    """
    Get a structured-output LLM with runtime fallback.

    Each provider in the fallback chain gets its own .with_structured_output()
    wrapper, so the fallback is schema-aware at every level.
    """
    chain = _build_provider_chain(provider or settings.LLM_PROVIDER)
    if not chain:
        raise LLMException(
            "No LLM provider is configured. Set at least one of "
            "GEMINI_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY."
        )

    def make_structured(p: str):
        return _instantiate(p).with_structured_output(schema)

    try:
        primary_structured = make_structured(chain[0])
    except LLMException as e:
        raise LLMException(f"Primary provider failed to initialise: {e}") from e

    if len(chain) == 1:
        return primary_structured

    fallback_structured = []
    for p in chain[1:]:
        try:
            fallback_structured.append(make_structured(p))
        except LLMException:
            continue

    if not fallback_structured:
        return primary_structured

    return primary_structured.with_fallbacks(fallback_structured)

