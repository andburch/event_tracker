"""
scrape/artifacts.py -- Production artifact writer for scrape runs.

Saves intermediate pipeline stages (raw HTML, cleaned text, chunks, prompts,
LLM responses) to debug_artifacts/{source}/ so that debug scripts can inspect
what a production run actually saw without re-fetching or re-calling the LLM.

Filename layout matches what the debug/*.py scripts already read:
    page_{N}_raw.html
    page_{N}_cleaned.txt
    page_{N}_chunk_{M}.txt
    page_{N}_chunk_{M}_prompt.txt
    page_{N}_chunk_{M}_response.json

This module has no dependency on debug/utils.py -- production owns its own
tiny I/O helper so there's zero coupling to the debug tooling.
"""

import os, glob, logging

log = logging.getLogger(__name__)

ARTIFACT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_artifacts')


def prepare_source_dir(key: str) -> str:
    """mkdir debug_artifacts/{key}/ and remove stale page_* files from prior runs."""
    path = os.path.join(ARTIFACT_ROOT, key)
    os.makedirs(path, exist_ok=True)
    for stale in glob.glob(os.path.join(path, 'page_*')):
        try:
            os.remove(stale)
        except OSError:
            pass
    return path


def save(key: str, filename: str, content: str) -> str:
    """Write debug_artifacts/{key}/{filename}; return full path."""
    path = os.path.join(ARTIFACT_ROOT, key)
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath
