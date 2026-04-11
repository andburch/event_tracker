"""
database/models.py — SQLAlchemy ORM models for the Phoenix Events Recommender.

Tables
------
events                   — Scraped event records (one row per unique title+date).
feedback_history         — Immutable log of every thumbs-up / thumbs-down click.
user_profile             — Single-row table holding the active preference profile.
preference_profile_history — Append-only log of every AI-generated summary.
scraper_runs             — Audit log of every scraper execution.
llm_calls                — Per-call timing record for every LLM API call made.
groq_model_limits        — Per-model rate limits from Groq docs (seeded at startup).

The engine and Session factory are created at module import time so any file
that does `from database.models import Session` gets a ready-to-use factory.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime
import config


class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this."""
    pass


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

class Event(Base):
    """
    A single scraped event.

    Deduplication key: (title, date) — see llm_scraper.py scrape_and_save().
    The `score` column starts NULL and is populated by run_batch_scoring()
    after each scrape run. Keeping it nullable lets us distinguish "not yet
    scored" from "scored 0.0".
    """
    __tablename__ = 'events'

    id          = Column(Integer, primary_key=True)
    title       = Column(String(500), nullable=False)
    description = Column(Text)                          # May be empty for music venues
    venue       = Column(String(300))
    date        = Column(DateTime, nullable=False)
    url         = Column(String(1000))                  # Source page URL
    source      = Column(String(100))                   # Scraper source_name (e.g. 'mesa_gov')
    category    = Column(String(100))                   # Broad category (e.g. 'music', 'family')
    price       = Column(String(100))                   # Free-text price string (e.g. '$10', 'Free')
    score       = Column(Float, nullable=True)          # LLM relevance score 0.0–1.0; NULL = unscored
    pinned      = Column(Boolean, default=False, nullable=False, server_default='0')  # User's short list
    created_at  = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# FeedbackHistory
# ---------------------------------------------------------------------------

class FeedbackHistory(Base):
    """
    Immutable record of every thumbs-up / thumbs-down the user clicks.

    Event content (title, description, etc.) is snapshotted at click time so
    the feedback row remains meaningful even if the event is later deleted or
    re-scraped with different text.

    `event_id` is kept as a soft reference (nullable) rather than a foreign key
    so deleting an event doesn't cascade-delete its feedback history.
    """
    __tablename__ = 'feedback_history'

    id                = Column(Integer, primary_key=True)
    event_id          = Column(Integer, nullable=True)          # Soft ref; may be NULL if event deleted
    event_title       = Column(String(500), nullable=False)     # Snapshot at click time
    event_description = Column(Text)
    event_source      = Column(String(100))
    event_category    = Column(String(100))
    event_venue       = Column(String(300))
    interested        = Column(Boolean, nullable=False)         # True = liked, False = disliked
    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------

class UserProfile(Base):
    """
    Single-row table holding the active user preference profile.

    taste_prompt
        Written manually by the user on the /profile page. Describes their
        interests in plain English. Used verbatim in every scoring prompt.

    preference_summary
        AI-generated rolling summary of feedback history. Updated automatically
        every SUMMARY_THRESHOLD new feedbacks (see llm_filter.py). Merged with
        taste_prompt when scoring events.

    feedback_count_at_last_summary
        How many FeedbackHistory rows existed when the last summary was generated.
        Used to detect when enough new feedback has accumulated to warrant a refresh.

    last_summarized_at
        Timestamp of the most recent summary generation. Informational only.
    """
    __tablename__ = 'user_profile'

    id                            = Column(Integer, primary_key=True)
    taste_prompt                  = Column(Text, default='')
    preference_summary            = Column(Text, default='')        # AI-generated
    feedback_count_at_last_summary = Column(Integer, default=0)
    last_summarized_at            = Column(DateTime, nullable=True)
    updated_at                    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# PreferenceProfileHistory
# ---------------------------------------------------------------------------

class PreferenceProfileHistory(Base):
    """
    Append-only log of every preference summary ever generated.

    Before overwriting preference_summary in UserProfile, the old value is
    archived here. This lets you see how your taste profile evolved over time
    and roll back if the AI produces a bad summary.
    """
    __tablename__ = 'preference_profile_history'

    id                 = Column(Integer, primary_key=True)
    taste_prompt       = Column(Text)       # Snapshot of taste_prompt at generation time
    preference_summary = Column(Text)       # The summary that was replaced (the old one)
    feedback_count     = Column(Integer)    # How many feedbacks were incorporated
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# ScraperRun
# ---------------------------------------------------------------------------

class ScraperRun(Base):
    """
    Audit log of every scraper execution.

    Written by scraper_runner.py after each scraper finishes (success or failure).
    Used by the /health dashboard to show yield trends and error rates.

    events_found  — Total events returned by scraper.scrape()
    events_added  — Subset that were new (not already in DB)
    success       — False if scraper raised an exception
    error_message — Exception string if success=False, else None
    duration_seconds — Wall-clock time for the scrape
    """
    __tablename__ = 'scraper_runs'

    id               = Column(Integer, primary_key=True)
    source           = Column(String(100), nullable=False)
    run_timestamp    = Column(DateTime, default=datetime.utcnow, nullable=False)
    events_found     = Column(Integer, nullable=False)
    events_added     = Column(Integer, nullable=False)
    success          = Column(Boolean, nullable=False)
    error_message    = Column(Text)
    duration_seconds = Column(Float)

    def __repr__(self):
        return (
            f"<ScraperRun(source='{self.source}', "
            f"timestamp='{self.run_timestamp}', "
            f"events={self.events_found})>"
        )


# ---------------------------------------------------------------------------
# LLMCall
# ---------------------------------------------------------------------------

class LLMCall(Base):
    """
    Per-call timing record for every LLM API call made by the app.

    Used to compare Groq vs Ollama performance on the /health dashboard.
    Written by llm_provider._log_call() after every successful call_llm() call.

    call_type: 'scraping', 'scoring', or 'summary'
    """
    __tablename__ = 'llm_calls'

    id                = Column(Integer, primary_key=True)
    timestamp         = Column(DateTime, default=datetime.utcnow, nullable=False)
    provider          = Column(String(50),  nullable=False)   # 'groq' or 'ollama'
    model             = Column(String(200), nullable=False)
    call_type         = Column(String(50),  nullable=False)   # 'scraping', 'scoring', 'summary'
    prompt_tokens     = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    duration_seconds  = Column(Float,   nullable=False)
    api_key_label     = Column(String(50), nullable=True)  # 'groq_key_1', 'groq_key_2', 'ollama'


# ---------------------------------------------------------------------------
# GroqRateLimitEvent
# ---------------------------------------------------------------------------

class GroqRateLimitEvent(Base):
    """
    Persisted log of LLM errors: 429 rate-limits and non-429 failures.

    Stored so we can diagnose classification correctness after the fact —
    e.g. verify whether key2 really hit a daily limit or was misclassified.

    classified_as: 'daily', 'tpm' (429s), or 'error_400', 'error_503', 'error' (non-429s)
    error_snippet: first 500 chars of the raw error string
    """
    __tablename__ = 'groq_rate_limit_events'

    id              = Column(Integer, primary_key=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, nullable=False)
    api_key_label   = Column(String(50),  nullable=False)   # 'groq_key_1', 'groq_key_2', 'ollama'
    model           = Column(String(200), nullable=False)
    classified_as   = Column(String(20),  nullable=False)   # 'daily', 'tpm', 'error_400', 'error_503', 'error'
    retry_after_sec = Column(Integer,     nullable=True)    # parsed retry-after value (429s only)
    error_snippet   = Column(Text,        nullable=True)    # raw error text (truncated)


# ---------------------------------------------------------------------------
# GroqModelLimit
# ---------------------------------------------------------------------------

class GroqModelLimit(Base):
    """
    Rate limits for each Groq model on the free tier.

    Seeded at startup from Groq's published limits
    (https://console.groq.com/docs/rate-limits). Rows are never overwritten
    automatically — edit them manually if you upgrade to a paid plan or
    Groq changes their limits.

    tpd is nullable: some models (e.g. groq/compound) have no daily token cap.
    tpm is nullable: audio models (whisper) are measured in audio-minutes, not tokens.
    """
    __tablename__ = 'groq_model_limits'

    model      = Column(String(200), primary_key=True)
    rpm        = Column(Integer, nullable=True)   # requests per minute
    rpd        = Column(Integer, nullable=True)   # requests per day
    tpm        = Column(Integer, nullable=True)   # tokens per minute
    tpd        = Column(Integer, nullable=True)   # tokens per day (null = no daily token cap)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Engine + Session factory
# ---------------------------------------------------------------------------

# create_all is idempotent — safe to call on every import.
# New tables are created; existing ones are left untouched.
engine  = create_engine(config.DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Migrate: add api_key_label to llm_calls if upgrading from an older schema.
# SQLAlchemy's create_all won't add columns to existing tables, so we do it
# manually. This is a no-op if the column already exists.
with engine.connect() as _conn:
    _cols = [r[1] for r in _conn.execute(text("PRAGMA table_info(llm_calls)")).fetchall()]
    if 'api_key_label' not in _cols:
        _conn.execute(text("ALTER TABLE llm_calls ADD COLUMN api_key_label TEXT"))
        _conn.commit()

# Seed groq_model_limits with free-tier limits from:
# https://console.groq.com/docs/rate-limits
# Rows are only inserted if they don't already exist, so manual edits
# (e.g. upgrading to a paid tier) are preserved across restarts.
_GROQ_LIMITS_SEED = [
    # model                                      rpm    rpd      tpm     tpd
    ('allam-2-7b',                               30,    7000,    6000,   500000),
    ('canopylabs/orpheus-arabic-saudi',          10,    100,     1200,   3600),
    ('canopylabs/orpheus-v1-english',            10,    100,     1200,   3600),
    ('groq/compound',                            30,    250,     70000,  None),
    ('groq/compound-mini',                       30,    250,     70000,  None),
    ('llama-3.1-8b-instant',                     30,    14400,   6000,   500000),
    ('llama-3.3-70b-versatile',                  30,    1000,    12000,  100000),
    ('meta-llama/llama-4-scout-17b-16e-instruct',30,    1000,    30000,  500000),
    ('meta-llama/llama-prompt-guard-2-22m',      30,    14400,   15000,  500000),
    ('meta-llama/llama-prompt-guard-2-86m',      30,    14400,   15000,  500000),
    ('moonshotai/kimi-k2-instruct',              60,    1000,    10000,  300000),
    ('moonshotai/kimi-k2-instruct-0905',         60,    1000,    10000,  300000),
    ('openai/gpt-oss-120b',                      30,    1000,    8000,   200000),
    ('openai/gpt-oss-20b',                       30,    1000,    8000,   200000),
    ('openai/gpt-oss-safeguard-20b',             30,    1000,    8000,   200000),
    ('qwen/qwen3-32b',                           60,    1000,    6000,   500000),
    ('whisper-large-v3',                         20,    2000,    None,   None),
    ('whisper-large-v3-turbo',                   20,    2000,    None,   None),
]
with engine.connect() as _conn:
    _existing = {
        r[0] for r in _conn.execute(text("SELECT model FROM groq_model_limits")).fetchall()
    }
    for _model, _rpm, _rpd, _tpm, _tpd in _GROQ_LIMITS_SEED:
        if _model not in _existing:
            _conn.execute(text(
                "INSERT INTO groq_model_limits (model, rpm, rpd, tpm, tpd) "
                "VALUES (:model, :rpm, :rpd, :tpm, :tpd)"
            ), {'model': _model, 'rpm': _rpm, 'rpd': _rpd, 'tpm': _tpm, 'tpd': _tpd})
    _conn.commit()
