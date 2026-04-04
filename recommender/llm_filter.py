"""
recommender/llm_filter.py — LLM-based event scoring and preference summarization.

Powered by Groq. Two distinct LLM tasks live here:

1. Batch scoring (run_batch_scoring)
   After each scrape, score every unscored future event against the user's
   taste profile. Scores are cached in Event.score (0.0-1.0) so the web UI
   can sort by relevance without making live API calls.

2. Rolling preference summary (maybe_update_preference_summary)
   Every SUMMARY_THRESHOLD new feedback clicks, merge the new liked/disliked
   events into the existing preference_summary using a larger, smarter model.
   The summary is stored in UserProfile.preference_summary and injected into
   every scoring prompt so the model learns from user behavior over time.

Models
------
SCORE_MODEL   llama-3.1-8b-instant    Fast and cheap; scoring is simple 0-1 classification
SUMMARY_MODEL llama-3.3-70b-versatile Better reasoning for nuanced preference summarization

SSL note
--------
The corporate network uses a self-signed certificate. The Groq SDK uses httpx
internally, so we pass a custom httpx.Client with verify=False to bypass it.
"""

import json
import time
import logging
import httpx
from groq import Groq, RateLimitError, APIStatusError
from datetime import datetime
import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------
# Models are configured in config.py and can be changed without code modifications
SCORE_MODEL       = config.LLM_SCORING_MODEL      # Model for batch scoring
SUMMARY_MODEL     = config.LLM_SCORING_MODEL      # Model for preference summarization

# ---------------------------------------------------------------------------
# Groq client (lazy singleton)
# ---------------------------------------------------------------------------

_client = None


def _get_client() -> Groq:
    """
    Return the shared Groq client, creating it on first call.

    Uses a custom httpx transport with SSL verification disabled to work
    behind the corporate firewall's self-signed certificate.
    """
    global _client
    if _client is None:
        transport   = httpx.HTTPTransport(verify=False)  # Corporate firewall SSL bypass
        http_client = httpx.Client(transport=transport, timeout=60)
        _client     = Groq(api_key=config.GROQ_API_KEY, http_client=http_client)
    return _client


def _api_available() -> bool:
    """Return True if a real Groq API key is configured."""
    return bool(config.GROQ_API_KEY and config.GROQ_API_KEY != 'your_groq_api_key_here')


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _call_with_retry(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential backoff on rate limit errors.

    Retries up to config.SCORING_MAX_RETRIES times. Delay doubles each attempt (5s, 10s, 20s).
    Re-raises on final failure or on non-rate-limit API errors.
    """
    max_retries = config.SCORING_MAX_RETRIES
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except RateLimitError as e:
            wait = config.SCORING_RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(f"Rate limit hit (attempt {attempt+1}/{max_retries}). Waiting {wait}s... [{e}]")
            if attempt < max_retries - 1:
                time.sleep(wait)
            else:
                log.error(f"Rate limit exceeded after {max_retries} attempts. Giving up.")
                raise
        except APIStatusError as e:
            # Non-retryable API error (e.g. invalid key, bad request)
            log.error(f"Groq API error (status {e.status_code}): {e.message}")
            raise
        except Exception as e:
            log.error(f"Unexpected error calling Groq: {e}")
            raise


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def get_profile():
    """
    Return the active UserProfile row, creating a blank one if none exists.

    The profile holds two text fields used in scoring:
      taste_prompt       — Written by the user; describes their interests
      preference_summary — AI-generated; updated from feedback history
    """
    from database.models import Session, UserProfile
    session = Session()
    try:
        profile = session.query(UserProfile).first()
        if not profile:
            profile = UserProfile(
                taste_prompt='',
                preference_summary='',
                feedback_count_at_last_summary=0,
            )
            session.add(profile)
            session.commit()
        return profile
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Score retrieval (used by web server)
# ---------------------------------------------------------------------------

def score_events(events: list) -> list[tuple]:
    """
    Return list of (event, score) tuples using cached DB scores.

    No LLM call is made here — scores are pre-computed by run_batch_scoring()
    after each scrape. Events with no score yet get a neutral 0.5 fallback
    so they appear in the middle of score-sorted lists rather than at the top
    or bottom.

    Args:
        events: List of Event ORM objects.

    Returns:
        List of (Event, float) tuples.
    """
    return [(ev, ev.score if ev.score is not None else 0.5) for ev in events]


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------

def run_batch_scoring(session=None, rescore_all: bool = False) -> None:
    """
    Score future events in chunked LLM calls and write scores back to the DB.

    By default only scores events where score IS NULL (new events from the
    latest scrape). Pass rescore_all=True to re-score everything — useful
    after updating the taste profile.

    Progress is committed after each chunk so a mid-run failure doesn't lose
    all previously scored events.

    Args:
        session: Optional existing SQLAlchemy session. If None, one is
                 created and closed internally.
        rescore_all: If True, re-score all future events regardless of current score.
    """
    from database.models import Session as MakeSession, Event, UserProfile
    own_session = session is None
    if own_session:
        session = MakeSession()

    try:
        profile = session.query(UserProfile).first()
        taste_prompt       = profile.taste_prompt.strip()       if profile else ''
        preference_summary = profile.preference_summary.strip() if profile else ''

        # Nothing to score against — skip silently
        if not taste_prompt and not preference_summary:
            log.info("No taste profile configured — skipping batch scoring")
            print("No taste profile configured — skipping batch scoring")
            return

        if not _api_available():
            log.warning("Groq API key not configured — skipping batch scoring")
            print("Groq not configured — skipping batch scoring")
            return

        # Build query: future events only, optionally filtered to unscored
        query = session.query(Event).filter(Event.date >= datetime.now())
        if not rescore_all:
            query = query.filter(Event.score.is_(None))

        events = query.all()
        if not events:
            print("No events to score.")
            return

        label = "all future" if rescore_all else "unscored"
        chunk_size = config.SCORING_CHUNK_SIZE
        print(f"Batch scoring {len(events)} {label} events in chunks of {chunk_size}...")
        log.info(f"Batch scoring {len(events)} {label} events")

        all_scores = {}  # Accumulate {event_id: score} across all chunks for final summary

        for i in range(0, len(events), chunk_size):
            chunk      = events[i:i + chunk_size]
            chunk_num  = i // chunk_size + 1
            total_chunks = (len(events) + chunk_size - 1) // chunk_size

            try:
                chunk_scores = _call_batch_score(chunk, taste_prompt, preference_summary)
                all_scores.update(chunk_scores)

                # Write scores to DB immediately — don't wait for all chunks
                for event in chunk:
                    if event.id in chunk_scores:
                        event.score = chunk_scores[event.id]
                session.commit()

                print(f"  Chunk {chunk_num}/{total_chunks} done ({len(chunk_scores)} scored)")

                # Throttle to stay under Groq free-tier token rate limit
                if i + chunk_size < len(events):
                    time.sleep(config.SCORING_CHUNK_DELAY)

            except Exception as e:
                log.error(f"Chunk {chunk_num} failed permanently: {e}")
                print(f"  Chunk {chunk_num}/{total_chunks} failed: {e}")
                # Continue to next chunk rather than aborting the whole batch

        total_scored = sum(1 for ev in events if ev.id in all_scores)
        print(f"Scored {total_scored}/{len(events)} events")

    finally:
        if own_session:
            session.close()


def _call_batch_score(events: list, taste_prompt: str, preference_summary: str) -> dict[int, float]:
    """
    Make one Groq API call to score a chunk of events.

    Builds a compact JSON representation of the events (id, title, first 150
    chars of description, venue, category) to keep token usage low.

    The model is instructed to return a raw JSON array with no markdown fences.
    We strip fences defensively in case the model ignores that instruction.

    Args:
        events: List of Event ORM objects (one chunk).
        taste_prompt: User-written interest description.
        preference_summary: AI-generated summary of past feedback.

    Returns:
        Dict mapping event_id (int) -> score (float 0.0-1.0).
        Only includes IDs that were in the input and returned valid scores.
    """
    valid_ids = {ev.id for ev in events}

    # Build compact JSON lines — truncate descriptions to keep token count low
    event_lines = []
    for ev in events:
        desc = (ev.description or '')[:150].replace('\n', ' ')
        event_lines.append(
            f'{{"id":{ev.id},"title":{json.dumps(ev.title)},'
            f'"desc":{json.dumps(desc)},'
            f'"venue":{json.dumps(ev.venue or "")},'
            f'"category":{json.dumps(ev.category or "")}}}'
        )
    events_json = '[\n' + ',\n'.join(event_lines) + '\n]'

    # Build the profile section — only include non-empty parts
    profile_section = ''
    if taste_prompt:
        profile_section += f'USER INTERESTS:\n{taste_prompt}\n\n'
    if preference_summary:
        profile_section += f'LEARNED PREFERENCES (from past feedback):\n{preference_summary}\n\n'

    # Prompt uses plain ASCII only — no em-dashes or smart quotes, which cause
    # encoding errors on Windows terminals.
    prompt = (
        f'{profile_section}'
        'TASK: Score each event for relevance to this specific user on a scale of 0.0 to 1.0.\n\n'
        'SCORING RULES:\n'
        '- 0.8 to 1.0: Strong match - directly aligns with stated interests or learned preferences\n'
        '- 0.5 to 0.7: Partial match - somewhat relevant, user might be interested\n'
        '- 0.2 to 0.4: Weak match - unlikely to interest this user\n'
        '- 0.0 to 0.1: No match - conflicts with stated dislikes or completely irrelevant\n\n'
        'STRICT OUTPUT RULES:\n'
        '- Respond with ONLY a raw JSON array. No explanation, no markdown, no code fences.\n'
        '- Every event ID from the input MUST appear in the output.\n'
        '- Do NOT invent IDs or omit any.\n'
        '- Format exactly: [{"id": <integer>, "score": <float 0.0-1.0>}, ...]\n\n'
        f'Events to score:\n{events_json}'
    )

    try:
        response = _call_with_retry(
            _get_client().chat.completions.create,
            model=SCORE_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,  # Low temperature for consistent, deterministic scoring
        )
        raw = response.choices[0].message.content.strip()

        # Defensively strip markdown code fences if the model ignores our instructions
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        results = json.loads(raw)

        # Validate each result: must have a known ID and a numeric score
        scores = {}
        for item in results:
            eid   = item.get('id')
            score = item.get('score')
            if eid in valid_ids and isinstance(score, (int, float)):
                # Clamp to [0.0, 1.0] in case the model goes slightly out of range
                scores[eid] = max(0.0, min(1.0, float(score)))

        # Log if the model dropped any IDs (shouldn't happen with strict prompt)
        missing = valid_ids - set(scores.keys())
        if missing:
            log.warning(
                f"Model returned scores for {len(scores)}/{len(valid_ids)} events. "
                f"Missing IDs: {missing}"
            )

        return scores

    except json.JSONDecodeError as e:
        log.error(f"Failed to parse scoring response as JSON: {e}\nRaw response: {raw[:500]}")
        return {}
    except Exception as e:
        log.error(f"Batch scoring chunk failed: {e}")
        raise  # Propagate so run_batch_scoring can log and continue to next chunk


# ---------------------------------------------------------------------------
# Preference summary
# ---------------------------------------------------------------------------

def maybe_update_preference_summary() -> None:
    """
    Check if enough new feedback has accumulated to warrant a summary refresh.

    Called from the /feedback endpoint after every thumbs-up / thumbs-down.
    Does nothing if fewer than config.SUMMARY_THRESHOLD new feedbacks have arrived
    since the last summary generation.

    When a new summary is generated:
    1. The old summary is archived to PreferenceProfileHistory.
    2. UserProfile.preference_summary is updated with the new text.
    3. feedback_count_at_last_summary is bumped to the current total.
    """
    from database.models import Session, UserProfile, FeedbackHistory, PreferenceProfileHistory
    if not _api_available():
        return

    session = Session()
    try:
        profile = session.query(UserProfile).first()
        if not profile:
            return

        total_feedback   = session.query(FeedbackHistory).count()
        new_since_last   = total_feedback - (profile.feedback_count_at_last_summary or 0)

        # Not enough new feedback yet — skip
        if new_since_last < config.SUMMARY_THRESHOLD:
            return

        print(f"Updating preference summary ({new_since_last} new feedbacks)...")
        log.info(f"Updating preference summary ({new_since_last} new feedbacks)")

        # Fetch only the new feedback rows (most recent N)
        new_feedback = session.query(FeedbackHistory).order_by(
            FeedbackHistory.created_at.desc()
        ).limit(new_since_last).all()

        new_summary = _generate_rolling_summary(
            existing_summary=profile.preference_summary or '',
            taste_prompt=profile.taste_prompt or '',
            new_feedback=new_feedback,
        )

        if new_summary:
            # Archive the old summary before overwriting
            if profile.preference_summary:
                session.add(PreferenceProfileHistory(
                    taste_prompt=profile.taste_prompt,
                    preference_summary=profile.preference_summary,
                    feedback_count=profile.feedback_count_at_last_summary,
                ))

            profile.preference_summary             = new_summary
            profile.feedback_count_at_last_summary = total_feedback
            profile.last_summarized_at             = datetime.utcnow()
            session.commit()
            print("Preference summary updated.")
            log.info("Preference summary updated.")

    except Exception as e:
        log.error(f"Error updating preference summary: {e}")
        print(f"Error updating preference summary: {e}")
        session.rollback()
    finally:
        session.close()


def _generate_rolling_summary(
    existing_summary: str,
    taste_prompt: str,
    new_feedback: list,
) -> str | None:
    """
    Merge new feedback into the existing preference summary using Groq.

    Two prompt variants:
    - If an existing summary exists: ask the model to update it with new signals.
    - If no summary yet: ask the model to write one from scratch.

    The model is instructed to infer themes and genres rather than naming
    specific events or venues, so the summary stays general and reusable.

    Args:
        existing_summary: Current preference_summary text (may be empty).
        taste_prompt:     User-written interest description (for context).
        new_feedback:     List of FeedbackHistory rows to incorporate.

    Returns:
        Updated summary string, or None if the API call failed.
    """
    liked    = [f for f in new_feedback if f.interested]
    disliked = [f for f in new_feedback if not f.interested]

    def fmt(fb_list: list) -> str:
        """Format a list of feedback rows as bullet lines for the prompt."""
        lines = []
        for f in fb_list:
            desc = (f.event_description or '')[:100].replace('\n', ' ')
            lines.append(f'- "{f.event_title}" ({f.event_source}) -- {desc}')
        return '\n'.join(lines) if lines else '(none)'

    if existing_summary:
        # Update mode: merge new signals into the existing profile
        prompt = (
            f'CURRENT PREFERENCE PROFILE:\n{existing_summary}\n\n'
            f'NEW EVENTS THE USER LIKED:\n{fmt(liked)}\n\n'
            f'NEW EVENTS THE USER DISLIKED:\n{fmt(disliked)}\n\n'
            'Update the preference profile to incorporate these new signals.\n'
            'RULES:\n'
            '- Keep it concise: 3 to 5 bullet points per section (Likes / Dislikes)\n'
            '- Strengthen language for reinforced signals, soften or revise contradictions\n'
            '- Do NOT mention specific event names, venue names, or source names\n'
            '- Infer underlying themes, genres, and activity types only\n'
            '- Output ONLY the updated profile text, no preamble, no explanation'
        )
    else:
        # First-time mode: write a profile from scratch
        prompt = (
            f'A user reacted to the following events.\n\n'
            f'LIKED:\n{fmt(liked)}\n\n'
            f'DISLIKED:\n{fmt(disliked)}\n\n'
            'Write a concise preference profile with two sections: Likes and Dislikes.\n'
            'RULES:\n'
            '- 3 to 5 bullet points per section\n'
            '- Do NOT mention specific event names, venue names, or source names\n'
            '- Infer underlying themes, genres, and activity types only\n'
            '- Output ONLY the profile text, no preamble, no explanation'
        )

    try:
        response = _call_with_retry(
            _get_client().chat.completions.create,
            model=SUMMARY_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.4,  # Slightly higher than scoring — allows more nuanced language
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"Summary generation failed: {e}")
        print(f"Summary generation failed: {e}")
        return None
