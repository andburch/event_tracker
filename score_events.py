#!/usr/bin/env python3
"""
score_events.py -- Run LLM batch scoring on all unscored events.

Run this separately after scraping is complete:
    python score_events.py
"""

from recommender.llm_filter import run_batch_scoring

if __name__ == '__main__':
    print("Running batch event scoring...")
    run_batch_scoring()
    print("Done!")
