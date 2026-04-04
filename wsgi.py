"""
Gunicorn entry point.

Usage: gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 wsgi:app
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.app import app  # noqa: F401  -- Gunicorn reads this symbol
