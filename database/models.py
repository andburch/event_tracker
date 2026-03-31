"""
database/models.py — SQLAlchemy ORM models for the Phoenix Events Recommender.

Tables
------
events                   — Scraped event records (one row per unique title+date).
feedback_history         — Immutable log of every thumbs-up / thumbs-down click.
user_profile             — Single-row table holding the active preference profile.
preference_profile_history — Append-only log of every AI-generated summary.
scraper_runs             — Audit log of every scraper execution.

The engine and Session factory are created at module import time so any file
that does `from database.models import Session` gets a ready-to-use factory.
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean
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
# Engine + Session factory
# ---------------------------------------------------------------------------

# create_all is idempotent — safe to call on every import.
# New tables are created; existing ones are left untouched.
engine  = create_engine(config.DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
