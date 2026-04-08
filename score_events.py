#!/usr/bin/env python3
"""
score_events.py -- Run LLM batch scoring on events.

IMPORTANT: This is a MANUAL step. Nothing in the scrape pipeline or web UI
triggers it automatically. Run it yourself after scraping, or after changing
your taste profile at /profile.

Usage:
    python score_events.py            # Score only events where score IS NULL
                                      # (new events from the most recent scrape)
    python score_events.py --all      # Re-score every future event — use this
                                      # after editing your taste profile or
                                      # after the rolling preference summary
                                      # has been updated by accumulated feedback.

Scoring shares the multi-key Groq rate limiter with scraping via
llm_provider.call_llm(), so it will switch keys/models on 429, classify
TPM vs daily limits, and fall back to Ollama if all Groq combinations are
daily-exhausted.
"""

import sys
from recommender.llm_filter import run_batch_scoring


if __name__ == '__main__':
    rescore_all = '--all' in sys.argv

    if rescore_all:
        print("Re-scoring ALL future events (rescore_all=True)...")
    else:
        print("Scoring unscored events only (pass --all to re-score everything)...")

    run_batch_scoring(rescore_all=rescore_all)
    print("Done!")
