"""
llm_provider.py — Unified LLM provider abstraction.

Supports Groq and Ollama via the OpenAI-compatible API.
Both providers use the same client interface; only the base_url and api_key differ.

Usage:
    from llm_provider import chat_complete

    # Use the default provider (config.LLM_PROVIDER)
    content = chat_complete(messages=[...], call_type='scraping')

    # Override per-call
    content = chat_complete(messages=[...], call_type='scraping', provider='ollama')
    content = chat_complete(messages=[...], call_type='scoring',  provider='groq')

Every call is timed and logged to the LLMCall table for provider comparison.
"""

import time
import httpx
import logging
import config

log = logging.getLogger(__name__)

# One cached OpenAI-compatible client per provider
_clients = {}

# Model resolution: (provider, call_type) -> model name from config
_MODELS = {
    ('groq',   'scraping'): lambda: config.LLM_SCRAPING_MODEL,
    ('groq',   'scoring'):  lambda: config.LLM_SCORING_MODEL,
    ('groq',   'summary'):  lambda: config.LLM_SCORING_MODEL,
    ('ollama', 'scraping'): lambda: config.OLLAMA_SCRAPING_MODEL,
    ('ollama', 'scoring'):  lambda: config.OLLAMA_SCORING_MODEL,
    ('ollama', 'summary'):  lambda: config.OLLAMA_SCORING_MODEL,
}


def get_client(provider: str = None):
    """Return a cached OpenAI-compatible client for the given provider."""
    provider = provider or config.LLM_PROVIDER
    if provider not in _clients:
        from openai import OpenAI
        if provider == 'ollama':
            _clients[provider] = OpenAI(
                base_url=f"{config.OLLAMA_URL}/v1",
                api_key='ollama',
                http_client=httpx.Client(timeout=config.OLLAMA_TIMEOUT),
            )
        else:  # groq
            _clients[provider] = OpenAI(
                base_url='https://api.groq.com/openai/v1',
                api_key=config.GROQ_API_KEY,
                http_client=httpx.Client(
                    transport=httpx.HTTPTransport(verify=False),
                    timeout=60,
                ),
            )
    return _clients[provider]


def chat_complete(
    messages: list,
    call_type: str = 'scraping',
    temperature: float = 0.1,
    response_format: dict = None,
    provider: str = None,
) -> str:
    """
    Make a single LLM chat completion call.

    Args:
        messages:        OpenAI-format messages list
        call_type:       'scraping', 'scoring', or 'summary' — used to resolve model
        temperature:     Sampling temperature
        response_format: e.g. {'type': 'json_object'} for structured output
        provider:        'groq' | 'ollama' | None (uses config.LLM_PROVIDER default)

    Returns:
        Response content string.

    Raises:
        Exception on API failure — callers are responsible for retry logic.
    """
    provider = provider or config.LLM_PROVIDER
    model = _MODELS[(provider, call_type)]()
    client = get_client(provider)

    kwargs = dict(model=model, messages=messages, temperature=temperature)
    if response_format:
        kwargs['response_format'] = response_format

    start = time.time()
    response = client.chat.completions.create(**kwargs)
    duration = time.time() - start

    usage = response.usage
    _log_call(
        provider=provider,
        model=model,
        call_type=call_type,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        duration_seconds=duration,
    )

    return response.choices[0].message.content


def is_available(provider: str = None) -> bool:
    """Return True if the given provider appears to be configured."""
    provider = provider or config.LLM_PROVIDER
    if provider == 'ollama':
        return bool(config.OLLAMA_URL)
    return bool(config.GROQ_API_KEY and config.GROQ_API_KEY != 'your_groq_api_key_here')


def _log_call(provider, model, call_type, prompt_tokens, completion_tokens, duration_seconds):
    """Write an LLMCall timing record to the database. Silently swallows errors."""
    from database.models import Session, LLMCall
    session = Session()
    try:
        session.add(LLMCall(
            provider=provider,
            model=model,
            call_type=call_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_seconds=duration_seconds,
        ))
        session.commit()
    except Exception as e:
        log.warning(f"Failed to log LLM call: {e}")
    finally:
        session.close()
