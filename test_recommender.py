"""
Debug tool for the recommendation/scoring system.
Tests scoring against a small sample of real DB events without running scrapers.

Usage:
    python test_recommender.py              # score 5 random future events
    python test_recommender.py --n 10       # score 10 events
    python test_recommender.py --ids 1 2 3  # score specific event IDs
    python test_recommender.py --ping       # just test the Groq connection
"""
import argparse
import sys
import json
import logging
import httpx
from groq import Groq
import config

log = logging.getLogger(__name__)


def ping_groq():
    """Send a minimal request to verify the Groq connection works."""
    print(f"\nGroq API key: {config.GROQ_API_KEY[:12]}...{config.GROQ_API_KEY[-4:]}")
    print("Testing connection...\n")
    try:
        client = _make_client()
        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[{'role': 'user', 'content': 'Reply with just the word: OK'}],
            max_tokens=5,
        )
        print(f"SUCCESS: {response.choices[0].message.content.strip()}")
        return True
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False


def _make_client():
    """Build Groq client with SSL verification disabled."""
    # SSL verification disabled
    transport = httpx.HTTPTransport(verify=False)
    http_client = httpx.Client(transport=transport)
    return Groq(api_key=config.GROQ_API_KEY, http_client=http_client)


def score_sample(event_ids=None, n=5):
    from database.models import Session, Event, UserProfile
    from datetime import datetime

    session = Session()
    profile = session.query(UserProfile).first()

    taste_prompt       = profile.taste_prompt.strip()       if profile else ''
    preference_summary = profile.preference_summary.strip() if profile else ''

    if not taste_prompt and not preference_summary:
        print("WARNING: No taste profile set. Go to /profile and write an 'About Me' first.")

    if event_ids:
        events = session.query(Event).filter(Event.id.in_(event_ids)).all()
    else:
        events = (session.query(Event)
                  .filter(Event.date >= datetime.now())
                  .order_by(Event.date)
                  .limit(n)
                  .all())

    if not events:
        print("No events found.")
        session.close()
        return

    print(f"\nProfile taste_prompt: {taste_prompt[:100] or '(none)'}")
    print(f"Preference summary:   {preference_summary[:100] or '(none)'}\n")
    print(f"Scoring {len(events)} events...\n")

    # Build prompt inline so we can print it for inspection
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

    profile_section = ''
    if taste_prompt:
        profile_section += f'USER INTERESTS:\n{taste_prompt}\n\n'
    if preference_summary:
        profile_section += f'LEARNED PREFERENCES (from past feedback):\n{preference_summary}\n\n'

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

    print("--- PROMPT SENT TO GROQ ---")
    print(prompt[:1500], "..." if len(prompt) > 1500 else "")
    print("---\n")

    try:
        client = _make_client()
        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        print("--- RAW RESPONSE ---")
        print(raw)
        print("---\n")

        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        results = json.loads(raw)
        score_map = {item['id']: item['score'] for item in results}

        print(f"{'ID':<6} {'Score':<7} {'Title':<50} {'Venue'}")
        print("-" * 90)
        for ev in events:
            score = score_map.get(ev.id, '???')
            score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
            print(f"{ev.id:<6} {score_str:<7} {ev.title[:50]:<50} {ev.venue or ''}")

    except Exception as e:
        print(f"\nFAILED: {type(e).__name__}: {e}")

    session.close()


if __name__ == '__main__':
    # Configure logging only when run as main script
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    
    parser = argparse.ArgumentParser(description='Test the Groq recommendation system')
    parser.add_argument('--ping', action='store_true', help='Just test the connection')
    parser.add_argument('--n', type=int, default=5, help='Number of events to score (default 5)')
    parser.add_argument('--ids', type=int, nargs='+', help='Specific event IDs to score')
    args = parser.parse_args()

    if args.ping:
        ping_groq()
    else:
        score_sample(event_ids=args.ids, n=args.n)
