"""
llm_provider.py — Unified LLM provider abstraction.

Supports Groq and Ollama via the OpenAI-compatible API.
Both providers use the same client interface; only the base_url and api_key differ.

Groq calls go through the rate limiter (groq_rate_limiter.py), which:
  - Tracks limits per (key, model) pair — a 429 on one combo doesn't block others
  - Switches between API keys and models on 429 errors
  - Distinguishes TPM limits (short wait) from daily limits (long wait)
  - Optionally falls back to Ollama when all (key, model) combos are daily-exhausted

Usage:
    from llm_provider import call_llm

    # Use the default provider (config.LLM_PROVIDER)
    content = call_llm(messages=[...], call_type='scraping')

    # Override per-call
    content = call_llm(messages=[...], call_type='scraping', provider='ollama')
    content = call_llm(messages=[...], call_type='scoring',  provider='groq')

Every call is timed and logged to the LLMCall table for provider comparison.
"""

import time
import httpx
import logging
import openai
import config

log = logging.getLogger(__name__)

# Cached OpenAI-compatible clients, keyed by (provider, key_label).
# Groq: one client per key label ('groq_key_1', 'groq_key_2').
# Ollama: one client, keyed as ('ollama', 'ollama').
_clients: dict[tuple[str, str], openai.OpenAI] = {}

# Model resolution for Ollama (Groq model is chosen by the rate limiter)
_OLLAMA_MODELS = {
    'scraping': lambda: config.OLLAMA_SCRAPING_MODEL,
    'scoring':  lambda: config.OLLAMA_SCORING_MODEL,
    'summary':  lambda: config.OLLAMA_SCORING_MODEL,
}


def _get_groq_client(label: str, api_key: str) -> openai.OpenAI:
    """Return (or create) a cached Groq client for the given key label."""
    cache_key = ('groq', label)
    if cache_key not in _clients:
        _clients[cache_key] = openai.OpenAI(
            base_url='https://api.groq.com/openai/v1',
            api_key=api_key,
            http_client=httpx.Client(
                transport=httpx.HTTPTransport(verify=False),
                timeout=60,
            ),
        )
    return _clients[cache_key]


def _get_ollama_client() -> openai.OpenAI:
    """Return (or create) the cached Ollama client."""
    cache_key = ('ollama', 'ollama')
    if cache_key not in _clients:
        _clients[cache_key] = openai.OpenAI(
            base_url=f"{config.OLLAMA_URL}/v1",
            api_key='ollama',
            http_client=httpx.Client(timeout=config.OLLAMA_TIMEOUT),
        )
    return _clients[cache_key]


# Legacy alias kept for any code that calls get_client() directly
def get_client(provider: str = None) -> openai.OpenAI:
    """Return a client for the given provider (uses primary Groq key or Ollama)."""
    provider = provider or config.LLM_PROVIDER
    if provider == 'ollama':
        return _get_ollama_client()
    if config.GROQ_API_KEY:
        return _get_groq_client('groq_key_1', config.GROQ_API_KEY)
    raise RuntimeError("No GROQ_API_KEY configured")


def call_llm(
    messages: list,
    call_type: str = 'scraping',
    temperature: float = 0.1,
    response_format: dict = None,
    provider: str = None,
) -> str:
    """
    Make a single LLM call.

    For Groq, uses the rate limiter to pick the best available (key, model)
    combination. On 429, switches combination or waits, then retries. If all
    combinations are daily-exhausted and GROQ_FALLBACK_TO_OLLAMA is set,
    falls back to Ollama.

    Args:
        messages:        OpenAI-format messages list
        call_type:       'scraping', 'scoring', or 'summary'
        temperature:     Sampling temperature
        response_format: e.g. {'type': 'json_object'} for structured output
        provider:        'groq' | 'ollama' | None (uses config.LLM_PROVIDER)

    Returns:
        Response content string.

    Raises:
        Exception on non-recoverable failure.
    """
    provider = provider or config.LLM_PROVIDER

    if provider == 'groq':
        return _call_llm_groq(messages, call_type, temperature, response_format)
    else:
        return _call_llm_ollama(messages, call_type, temperature, response_format)


def _call_llm_groq(messages, call_type, temperature, response_format) -> str:
    """
    Groq path: pick a (key, model) combination, call, handle 429 by switching.

    Tries up to (keys × models + 1) times, letting the rate limiter decide
    which combination to use each attempt.
    """
    from groq_rate_limiter import (
        pick_key_and_model, record_rate_limit, all_groq_combinations_daily_exhausted
    )

    models = config.LLM_SCRAPING_MODELS if call_type == 'scraping' else config.LLM_SCORING_MODELS
    max_attempts = len(models) * 2 + 1  # generous upper bound

    for attempt in range(max_attempts):
        try:
            label, api_key, model = pick_key_and_model(models)
        except RuntimeError:
            # All (key, model) combinations daily-exhausted
            if config.GROQ_FALLBACK_TO_OLLAMA:
                log.warning("[rate_limiter] All Groq combinations daily-exhausted, falling back to Ollama")
                print("\n  [rate_limiter] All Groq combinations daily-exhausted — using Ollama fallback")
                return _call_llm_ollama(messages, call_type, temperature, response_format)
            raise

        client = _get_groq_client(label, api_key)
        kwargs = dict(model=model, messages=messages, temperature=temperature)
        if response_format:
            kwargs['response_format'] = response_format

        start = time.time()
        try:
            response = client.chat.completions.create(**kwargs)
            duration = time.time() - start
            usage = response.usage
            _log_call(
                provider='groq',
                model=model,
                call_type=call_type,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                duration_seconds=duration,
                api_key_label=label,
            )
            return response.choices[0].message.content

        except openai.RateLimitError as e:
            record_rate_limit(label, model, e)  # classifies TPM vs daily via message + DB
            log.warning(
                f"[rate_limiter] 429 on {label}/{model} "
                f"(attempt {attempt+1}/{max_attempts})"
            )
            if attempt == max_attempts - 1:
                if config.GROQ_FALLBACK_TO_OLLAMA and all_groq_combinations_daily_exhausted(models):
                    log.warning("[rate_limiter] Falling back to Ollama after exhausting all Groq combos")
                    return _call_llm_ollama(messages, call_type, temperature, response_format)
                raise
            # Loop: pick_key_and_model() will choose a different combo or sleep


def _call_llm_ollama(messages, call_type, temperature, response_format) -> str:
    """Direct call to Ollama, no key switching."""
    model = _OLLAMA_MODELS[call_type]()
    client = _get_ollama_client()

    kwargs = dict(model=model, messages=messages, temperature=temperature,
                  max_tokens=config.OLLAMA_MAX_TOKENS)
    if response_format:
        kwargs['response_format'] = response_format

    start = time.time()
    response = client.chat.completions.create(**kwargs)
    duration = time.time() - start

    usage = response.usage
    _log_call(
        provider='ollama',
        model=model,
        call_type=call_type,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        duration_seconds=duration,
        api_key_label='ollama',
    )
    return response.choices[0].message.content


def is_available(provider: str = None) -> bool:
    """Return True if the given provider appears to be configured."""
    provider = provider or config.LLM_PROVIDER
    if provider == 'ollama':
        return bool(config.OLLAMA_URL)
    return bool(config.GROQ_API_KEY and config.GROQ_API_KEY != 'your_groq_api_key_here')


def _log_call(provider, model, call_type, prompt_tokens, completion_tokens,
              duration_seconds, api_key_label=None):
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
            api_key_label=api_key_label,
        ))
        session.commit()
    except Exception as e:
        log.warning(f"Failed to log LLM call: {e}")
    finally:
        session.close()
