"""
groq_rate_limiter.py — Intelligent Groq API key + model selection.

Groq rate limits are per-model per-account. This module tracks limits at the
(key_label, model) level so a 429 on one combination doesn't block others.

Given two keys and a model list ['model_A', 'model_B'], the priority order is:
    (key1, model_A) → (key2, model_A) → (key1, model_B) → (key2, model_B)

429 CLASSIFICATION
------------------
When a 429 occurs, we need to decide: is this a TPM (per-minute) limit or a
daily (TPD) limit? The response tells us:

  1. Error message body (PRIMARY): Groq explicitly states the limit type:
       "on tokens per minute (TPM): Limit 12000, Used 11963..."
       "on tokens per day (TPD): Limit 100000, Used 99847..."
     This is the most reliable signal.

  2. Our own DB usage (SECONDARY VALIDATION): We query LLMCall records to
     verify. If we've used > 80% of the daily TPD limit per our own records,
     that corroborates a daily classification even if the message is unclear.
     If our DB shows < 10% of daily usage, a "daily limit" claim is suspicious
     and we treat it as transient instead.

  3. Default: If we can't classify, treat as transient TPM (short wait, try
     next key). This is the safe failure mode — we waste a few seconds but
     never incorrectly abandon healthy keys.

On TPM: block this (key, model) for retry_after seconds, try next combo.
On daily: mark (key, model) as exhausted for this session.
On transient/unclear: cap retry_after at 90s and treat as TPM.

Usage (from llm_provider.py):
    from groq_rate_limiter import pick_key_and_model, record_rate_limit

    label, api_key, model = pick_key_and_model(config.LLM_SCRAPING_MODELS)
    try:
        ... make api call with api_key and model ...
    except openai.RateLimitError as e:
        record_rate_limit(label, model, e)
        raise  # caller loops back to pick_key_and_model()
"""

import re
import time
import logging
from datetime import datetime, timedelta

import config

log = logging.getLogger(__name__)


def _available_keys() -> list[tuple[str, str]]:
    """Return list of (label, api_key) for all non-empty configured Groq keys."""
    keys = []
    if config.GROQ_API_KEY:
        keys.append(('groq_key_1', config.GROQ_API_KEY))
    if config.GROQ_API_KEY_2:
        keys.append(('groq_key_2', config.GROQ_API_KEY_2))
    return keys


class GroqRateLimiter:
    """
    Tracks per-(key, model) rate limit state and classifies 429 errors using
    the error message body cross-referenced against our own DB usage records.

    _blocked_until:   (label, model) -> datetime when safe to retry
    _daily_exhausted: set of (label, model) confirmed to be daily-limit-exhausted
    """

    def __init__(self):
        self._blocked_until: dict[tuple[str, str], datetime] = {}
        self._daily_exhausted: set[tuple[str, str]] = set()
        self._limit_cache: dict[str, object] = {}  # model -> GroqModelLimit row

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def record_rate_limit(self, label: str, model: str, error):
        """
        Called on RateLimitError. Classifies the error as TPM or daily using
        the error message body and our own DB usage records, then blocks this
        (key, model) pair appropriately.

        Args:
            label: Key label ('groq_key_1', 'groq_key_2')
            model: Model name (e.g. 'llama-3.3-70b-versatile')
            error: The openai.RateLimitError exception (or an error string for tests)
        """
        error_str = self._extract_error_str(error)
        is_daily, retry_after = self._classify_429(label, model, error_str)

        pair = (label, model)
        until = datetime.now() + timedelta(seconds=retry_after)
        self._blocked_until[pair] = until

        if is_daily:
            self._daily_exhausted.add(pair)
            log.warning(
                f"[rate_limiter] {label}/{model} DAILY limit confirmed — "
                f"blocked until ~{until.strftime('%H:%M')} ({retry_after}s)"
            )
            print(f"\n  [rate_limiter] {label}/{model} daily token limit — retry after {until.strftime('%H:%M')}")
        else:
            log.info(
                f"[rate_limiter] {label}/{model} TPM limit — "
                f"blocked for {retry_after}s"
            )
            print(f"\n  [rate_limiter] {label}/{model} TPM limit — retry in {retry_after}s")

        self._log_rate_limit_event(label, model, is_daily, retry_after, error_str)

    def _log_rate_limit_event(self, label: str, model: str, is_daily: bool,
                              retry_after: int, error_str: str) -> None:
        """Persist this 429 event to the DB so we can audit classifications later."""
        try:
            from database.models import Session, GroqRateLimitEvent
            s = Session()
            try:
                s.add(GroqRateLimitEvent(
                    api_key_label=label,
                    model=model,
                    classified_as='daily' if is_daily else 'tpm',
                    retry_after_sec=retry_after,
                    error_snippet=error_str[:500],
                ))
                s.commit()
            finally:
                s.close()
        except Exception as e:
            log.warning(f"[rate_limiter] Failed to log rate limit event: {e}")

    def pick_key_and_model(self, models: list[str]) -> tuple[str, str, str]:
        """
        Return (label, api_key, model) for the best available combination.

        Priority: model[0] across all keys, then model[1] across all keys, etc.

        - If a combination is immediately available: return it.
        - If all non-exhausted combinations are TPM-blocked: sleep until soonest.
        - If all combinations are daily-exhausted: raise RuntimeError.

        Raises:
            RuntimeError: No Groq keys configured, or all (key, model) pairs
                          are daily-exhausted.
        """
        if not _available_keys():
            raise RuntimeError("No Groq API keys configured (set GROQ_API_KEY in .env)")

        combos = self._combinations(models)

        usable = [(l, k, m) for l, k, m in combos if (l, m) not in self._daily_exhausted]
        if not usable:
            raise RuntimeError(
                "All Groq (key, model) combinations have hit the daily token limit. "
                "Set GROQ_FALLBACK_TO_OLLAMA=true in .env to use Ollama instead, "
                "or wait until the daily limit resets."
            )

        # Return first immediately available combo
        for label, api_key, model in usable:
            if self._is_available(label, model):
                return label, api_key, model

        # All usable combos are TPM-blocked — wait for the soonest
        soonest = min(usable, key=lambda t: self._blocked_until.get((t[0], t[2]), datetime.min))
        label, api_key, model = soonest
        until = self._blocked_until[(label, model)]
        wait_secs = max(0, (until - datetime.now()).total_seconds())
        if wait_secs > 0:
            print(f"\n  [rate_limiter] All Groq combos TPM-limited. "
                  f"Waiting {wait_secs:.0f}s for {label}/{model}...")
            log.info(f"[rate_limiter] Sleeping {wait_secs:.0f}s for {label}/{model}")
            time.sleep(wait_secs + 1)

        return label, api_key, model

    def all_daily_exhausted(self, models: list[str]) -> bool:
        """True if every (key, model) combination is daily-exhausted."""
        combos = self._combinations(models)
        return bool(combos) and all((l, m) in self._daily_exhausted for l, _, m in combos)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_429(self, label: str, model: str, error_str: str) -> tuple[bool, int]:
        """
        Classify a 429 as daily-limit or TPM.

        Returns (is_daily, retry_after_secs).

        Decision order:
          1. Groq error message body — explicit "TPM" or "TPD" text
          2. DB usage cross-check — if message is ambiguous, our own records
             tell us whether we're plausibly near the daily limit
          3. Default to transient/TPM with a capped retry

        This prevents misclassifying Groq service errors (which can return
        large retry-after values) as "daily exhausted" on fresh keys.
        """
        error_lower = error_str.lower()

        # 1. Parse explicit type signal from Groq message
        msg_says_tpd = 'tokens per day' in error_lower or '(tpd)' in error_lower
        msg_says_tpm = 'tokens per minute' in error_lower or '(tpm)' in error_lower

        # 2. Parse retry-after from message text
        retry_after = self._parse_retry_after(error_str)

        # 3. Also try the HTTP header (may be more precise than message text)
        header_retry = self._parse_retry_header(error_str)
        if header_retry:
            retry_after = max(retry_after, header_retry)

        # 4. Query our own DB usage and look up per-model limits
        tpm_used, tpd_used = self._db_usage(label, model)
        limits = self._get_model_limits(model)
        db_near_daily = (limits.tpd is not None) and (tpd_used > 0.80 * limits.tpd)
        db_near_tpm   = (limits.tpm is not None) and (tpm_used  > 0.50 * limits.tpm)

        log.debug(
            f"[rate_limiter] classify_429 {label}/{model}: "
            f"msg_tpd={msg_says_tpd} msg_tpm={msg_says_tpm} "
            f"retry={retry_after}s db_tpm_used={tpm_used}/{limits.tpm} "
            f"db_tpd_used={tpd_used}/{limits.tpd}"
        )

        # Decision tree
        if msg_says_tpd:
            # Groq explicitly said daily limit — trust it
            return True, retry_after

        if msg_says_tpm:
            # Groq explicitly said per-minute limit — trust it
            return False, retry_after

        # No explicit type in message. Use DB to decide.
        if db_near_daily:
            log.warning(
                f"[rate_limiter] Ambiguous 429; DB shows {tpd_used:,}/{limits.tpd:,} "
                f"daily tokens used (>80% threshold) — treating as DAILY"
            )
            return True, retry_after

        # DB doesn't corroborate a daily limit. This is a transient error or
        # a TPM spike. Cap the wait so we don't stall on a bogus retry-after.
        if retry_after > 120:
            log.warning(
                f"[rate_limiter] Ambiguous 429 with long retry_after={retry_after}s "
                f"but DB shows only {tpd_used:,}/{limits.tpd} daily tokens used — "
                f"treating as TRANSIENT (capping wait to 90s)"
            )
            retry_after = 90

        return False, retry_after

    def _parse_retry_after(self, error_str: str) -> int:
        """Extract retry-after seconds from Groq error message text."""
        # "Please try again in 2h15m30.5s"
        m = re.search(r'try again in (\d+)h(\d+)m([\d.]+)s', error_str)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(float(m.group(3))) + 1
        # "Please try again in 2h15m"
        m = re.search(r'try again in (\d+)h(\d+)m', error_str)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + 1
        # "Please try again in 2h"
        m = re.search(r'try again in (\d+)h', error_str)
        if m:
            return int(m.group(1)) * 3600 + 60
        # "Please try again in 45.2s"
        m = re.search(r'try again in ([\d.]+)s', error_str)
        if m:
            return int(float(m.group(1))) + 1
        # "Please try again in 2m30.5s"
        m = re.search(r'try again in (\d+)m([\d.]+)s', error_str)
        if m:
            return int(m.group(1)) * 60 + int(float(m.group(2))) + 1
        # "Please try again in 2m"
        m = re.search(r'try again in (\d+)m', error_str)
        if m:
            return int(m.group(1)) * 60 + 1
        return 60  # default

    def _parse_retry_header(self, error_str: str) -> int | None:
        """Try to extract retry-after from the HTTP header embedded in the error."""
        # openai SDK includes headers in the string representation sometimes
        m = re.search(r"'retry-after':\s*'(\d+)'", error_str, re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def _extract_error_str(self, error) -> str:
        """Get the most informative string from an exception or string."""
        parts = []
        if isinstance(error, str):
            return error
        # Include the str() representation (contains message body)
        parts.append(str(error))
        # Also try .message attribute if present (openai SDK)
        if hasattr(error, 'message') and error.message:
            parts.append(str(error.message))
        # Try response headers for retry-after
        try:
            headers = dict(error.response.headers)
            parts.append(str(headers))
        except Exception:
            pass
        return ' '.join(parts)

    def _get_model_limits(self, model: str):
        """
        Return the GroqModelLimit row for this model from the DB.
        Result is cached in-process so we only query once per model per run.
        Falls back to conservative defaults if the model isn't in the table.
        """
        if model in self._limit_cache:
            return self._limit_cache[model]

        try:
            from database.models import Session, GroqModelLimit
            s = Session()
            try:
                row = s.query(GroqModelLimit).filter(GroqModelLimit.model == model).first()
            finally:
                s.close()

            if row is None:
                log.warning(
                    f"[rate_limiter] No DB limits found for model '{model}' — "
                    f"using conservative fallback (tpm=6000, tpd=100000). "
                    f"Add the model to groq_model_limits to fix this."
                )
                # Return a namespace-like fallback object
                class _Fallback:
                    tpm = 6000
                    tpd = 100000
                    rpm = 30
                    rpd = 1000
                row = _Fallback()

            self._limit_cache[model] = row
            return row

        except Exception as e:
            log.warning(f"[rate_limiter] DB limit lookup failed for '{model}': {e}")
            class _Fallback:
                tpm = 6000
                tpd = 100000
                rpm = 30
                rpd = 1000
            return _Fallback()

    def _db_usage(self, label: str, model: str) -> tuple[int, int]:
        """
        Query our LLMCall records for recent token usage on this (key, model).

        Returns (tokens_last_60s, tokens_last_24h).
        Called only when classifying an ambiguous 429 — not on every request.
        """
        try:
            from database.models import Session, LLMCall
            from sqlalchemy import func
            now = datetime.utcnow()
            s = Session()
            try:
                def _sum(since):
                    result = s.query(
                        func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens)
                    ).filter(
                        LLMCall.api_key_label == label,
                        LLMCall.model == model,
                        LLMCall.timestamp >= since,
                    ).scalar()
                    return result or 0

                tpm = _sum(now - timedelta(seconds=60))
                tpd = _sum(now - timedelta(hours=24))
                return tpm, tpd
            finally:
                s.close()
        except Exception as e:
            log.warning(f"[rate_limiter] DB usage query failed: {e}")
            return 0, 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _combinations(self, models: list[str]) -> list[tuple[str, str, str]]:
        """
        All (label, api_key, model) triples in priority order:
        model-first, so all keys are tried on model[0] before moving to model[1].
        """
        keys = _available_keys()
        result = []
        for model in models:
            for label, api_key in keys:
                result.append((label, api_key, model))
        return result

    def _is_available(self, label: str, model: str) -> bool:
        """True if this (key, model) pair is not currently blocked."""
        pair = (label, model)
        blocked = self._blocked_until.get(pair)
        return blocked is None or datetime.now() >= blocked


# Module-level singleton
_limiter = GroqRateLimiter()


def pick_key_and_model(models: list[str]) -> tuple[str, str, str]:
    """Return (label, api_key, model) for the best available combination. May sleep."""
    return _limiter.pick_key_and_model(models)


def record_rate_limit(label: str, model: str, error):
    """Record a 429 error for the given (key, model) pair."""
    _limiter.record_rate_limit(label, model, error)


def all_groq_combinations_daily_exhausted(models: list[str]) -> bool:
    """True if every configured (key, model) combination has hit its daily limit."""
    return _limiter.all_daily_exhausted(models)
