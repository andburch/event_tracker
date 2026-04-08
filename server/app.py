"""
server/app.py — Flask web application for the Phoenix Events Recommender.

Routes
------
GET  /           Event listing with source filter, date range filter, sort order
POST /feedback   Record a thumbs-up / thumbs-down for an event
GET  /health     Scraper health dashboard (yield trends, error rates)
GET  /calendar   Monthly calendar view of events
GET  /profile    View user taste profile and feedback history
POST /profile    Save updated taste_prompt

Run with:
    python server/app.py
Server starts on http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, redirect, Response
from urllib.parse import urlencode
import sys
import os

# Add project root to path so imports work when running from the server/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import (
    Session, Event, FeedbackHistory, UserProfile,
    PreferenceProfileHistory, ScraperRun, LLMCall, GroqModelLimit, GroqRateLimitEvent,
)
from recommender.llm_filter import score_events, get_profile, maybe_update_preference_summary
from datetime import datetime, timedelta, date
import calendar
from sqlalchemy import func
from sources import SITES, SOURCE_NAMES, SOURCE_COLORS

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Phoenix timezone helpers
# ---------------------------------------------------------------------------
# Phoenix does not observe DST — America/Phoenix is UTC-7 year-round (MST),
# so we can convert to/from UTC with a fixed 7h offset without pytz or
# zoneinfo. All metadata timestamps in the database (llm_calls, scraper_runs,
# feedback_history, preference_profile_history, groq_rate_limit_events, etc.)
# are stored as naive UTC via datetime.utcnow(); the UI converts them to
# Phoenix local time for display via the phoenix_time Jinja filter.
#
# NOTE: Event.date is a SEPARATE concept — those values are Phoenix local
# already (scraped verbatim from Phoenix-area websites), so they are NOT
# run through this conversion. See `index.html` / `calendar.html` where
# `event.date` is rendered with raw strftime.
#
# The sentinel time 12:34 (see CLAUDE.md) means "no specific time given" —
# treat those events as all-day when exporting to GCal/ICS.

_PHOENIX_UTC_OFFSET = timedelta(hours=7)


def utc_to_phoenix(dt: datetime) -> datetime:
    """Convert a naive UTC datetime to a naive Phoenix (MST, UTC-7) datetime."""
    if dt is None:
        return None
    return dt - _PHOENIX_UTC_OFFSET


def phoenix_now() -> datetime:
    """Return the current time as a naive Phoenix datetime."""
    return datetime.utcnow() - _PHOENIX_UTC_OFFSET


def phoenix_time_filter(dt: datetime, fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Jinja filter: convert a UTC datetime to Phoenix time and format it.

    Usage in templates:
        {{ some_utc_datetime | phoenix_time }}
        {{ some_utc_datetime | phoenix_time('%m-%d %H:%M') }}

    Returns an empty string for None so templates don't have to guard.
    """
    if dt is None:
        return ''
    return (dt - _PHOENIX_UTC_OFFSET).strftime(fmt)


def _is_all_day(dt: datetime) -> bool:
    """Events with the 12:34 sentinel time are treated as all-day."""
    return dt.hour == 12 and dt.minute == 34


def event_to_gcal_url(event) -> str:
    """
    Build a Google Calendar render-template URL that pre-fills a new event.

    Clicking the returned URL opens Google Calendar in a new tab with the
    title, date/time, description, and location already populated — the user
    just has to click Save.

    All-day events use the YYYYMMDD date format (end date is exclusive, so
    we add one day). Timed events default to a 2-hour block because the
    scraper rarely captures an end time.
    """
    start = event.date
    if _is_all_day(start):
        start_str = start.strftime('%Y%m%d')
        end_str = (start + timedelta(days=1)).strftime('%Y%m%d')
    else:
        end = start + timedelta(hours=2)
        start_str = start.strftime('%Y%m%dT%H%M%S')
        end_str = end.strftime('%Y%m%dT%H%M%S')

    params = {
        'action': 'TEMPLATE',
        'text': event.title or 'Event',
        'dates': f'{start_str}/{end_str}',
        'ctz': 'America/Phoenix',
    }

    details_parts = []
    if event.description:
        details_parts.append(event.description[:1500])
    if event.url:
        if details_parts:
            details_parts.append('\n\n')
        details_parts.append(f'Source: {event.url}')
    if details_parts:
        params['details'] = ''.join(details_parts)

    if event.venue:
        params['location'] = event.venue

    return 'https://calendar.google.com/calendar/render?' + urlencode(params)


def _ics_escape(s) -> str:
    """Escape text for insertion into an ICS property value per RFC 5545."""
    if s is None:
        return ''
    return (
        str(s)
        .replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\r\n', '\\n')
        .replace('\n', '\\n')
        .replace('\r', '\\n')
    )


def _ics_fold(line: str) -> str:
    """
    RFC 5545 line folding: lines longer than 75 octets must be split, with
    continuation lines starting with a single space. Most modern clients
    tolerate long lines, but folding is cheap and avoids surprises.
    """
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    rest = line[75:]
    while rest:
        chunks.append(' ' + rest[:74])
        rest = rest[74:]
    return '\r\n'.join(chunks)


def events_to_ics(events, calendar_name: str = 'Phoenix Events') -> str:
    """
    Build a minimal RFC 5545 ICS calendar containing the given events.

    Timed events are converted from Phoenix local time to UTC via the fixed
    +7h offset and emitted with the `Z` suffix, so no VTIMEZONE block is
    required. All-day events use `VALUE=DATE` with an exclusive end date.

    The returned string is ready to be served with
    `Content-Type: text/calendar`.
    """
    now_utc_stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Phoenix Events Recommender//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{_ics_escape(calendar_name)}',
    ]

    for ev in events:
        if _is_all_day(ev.date):
            dtstart_line = f'DTSTART;VALUE=DATE:{ev.date.strftime("%Y%m%d")}'
            dtend_line = f'DTEND;VALUE=DATE:{(ev.date + timedelta(days=1)).strftime("%Y%m%d")}'
        else:
            start_utc = ev.date + _PHOENIX_UTC_OFFSET
            end_utc = start_utc + timedelta(hours=2)
            dtstart_line = f'DTSTART:{start_utc.strftime("%Y%m%dT%H%M%SZ")}'
            dtend_line = f'DTEND:{end_utc.strftime("%Y%m%dT%H%M%SZ")}'

        # Compose description: event body + source URL footer
        desc_parts = []
        if ev.description:
            desc_parts.append(ev.description[:1500])
        if ev.url:
            if desc_parts:
                desc_parts.append('\n\n')
            desc_parts.append(f'Source: {ev.url}')
        description = ''.join(desc_parts)

        event_lines = [
            'BEGIN:VEVENT',
            f'UID:phoenix-events-{ev.id}@localhost',
            f'DTSTAMP:{now_utc_stamp}',
            dtstart_line,
            dtend_line,
            f'SUMMARY:{_ics_escape(ev.title)}',
        ]
        if description:
            event_lines.append(f'DESCRIPTION:{_ics_escape(description)}')
        if ev.venue:
            event_lines.append(f'LOCATION:{_ics_escape(ev.venue)}')
        if ev.url:
            event_lines.append(f'URL:{ev.url}')
        event_lines.append('END:VEVENT')

        lines.extend(_ics_fold(l) for l in event_lines)

    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines) + '\r\n'


# Register Jinja filters so templates can write `{{ event | gcal_url }}` and
# `{{ ts | phoenix_time('%m-%d %H:%M') }}` without extra route-side plumbing.
app.jinja_env.filters['gcal_url'] = event_to_gcal_url
app.jinja_env.filters['phoenix_time'] = phoenix_time_filter


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    """
    Main event listing page.

    Query parameters:
        sources     (multi-value) — Filter to specific source codes
        start_date  (YYYY-MM-DD)  — Only show events on or after this date
        end_date    (YYYY-MM-DD)  — Only show events on or before this date
        sort        'date'|'score' — Sort order (default: date)

    Events are scored via score_events() which reads cached Event.score values.
    No live LLM calls happen here.
    """
    session = Session()
    try:
        selected_sources = request.args.getlist('sources')  # Empty list = show all
        start_date = request.args.get('start_date', '')
        end_date   = request.args.get('end_date', '')
        sort_by    = request.args.get('sort', 'date')

        # Base query: only future events
        query = session.query(Event).filter(Event.date >= datetime.now())

        # Apply optional filters
        if selected_sources:
            query = query.filter(Event.source.in_(selected_sources))

        if start_date:
            try:
                query = query.filter(Event.date >= datetime.strptime(start_date, '%Y-%m-%d'))
            except ValueError:
                pass  # Ignore malformed date params

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                query = query.filter(Event.date <= end_dt)
            except ValueError:
                pass

        events = query.all()

        # Pinned events (shortlist) — always shown regardless of filters
        pinned_events = session.query(Event).filter(
            Event.pinned == True,
            Event.date >= datetime.now(),
        ).order_by(Event.date).all()

        # Build source list sorted alphabetically by display name for the filter dropdown
        raw_sources = [s[0] for s in session.query(Event.source).distinct().all()]
        sources = sorted(raw_sources, key=lambda s: SOURCE_NAMES.get(s, s))

        # Attach cached scores and sort
        scored_events = score_events(events)
        if sort_by == 'score':
            scored_events.sort(key=lambda x: x[1], reverse=True)
        else:
            scored_events.sort(key=lambda x: x[0].date)

        return render_template(
            'index.html',
            events=scored_events,
            pinned_events=pinned_events,
            sources=sources,
            source_names=SOURCE_NAMES,
            selected_sources=selected_sources,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
        )
    finally:
        session.close()


@app.route('/feedback', methods=['POST'])
def feedback():
    """
    Record a thumbs-up or thumbs-down for an event.

    Expects JSON body: {"event_id": <int>, "interested": <bool>}

    Snapshots the event's current content into FeedbackHistory so the record
    remains meaningful even if the event is later deleted or re-scraped.

    After writing feedback, calls maybe_update_preference_summary() which
    checks if enough new feedback has accumulated to trigger a summary refresh.
    """
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
    
    event_id = data.get('event_id')
    interested = data.get('interested')
    
    # Validate input
    if event_id is None:
        return jsonify({'status': 'error', 'message': 'event_id is required'}), 400
    if not isinstance(event_id, int):
        return jsonify({'status': 'error', 'message': 'event_id must be an integer'}), 400
    if interested is None:
        return jsonify({'status': 'error', 'message': 'interested is required'}), 400
    if not isinstance(interested, bool):
        return jsonify({'status': 'error', 'message': 'interested must be a boolean'}), 400

    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404

        # Snapshot event content at click time
        fb = FeedbackHistory(
            event_id=event.id,
            event_title=event.title,
            event_description=event.description,
            event_source=event.source,
            event_category=event.category,
            event_venue=event.venue,
            interested=interested,
        )
        session.add(fb)
        session.commit()
    finally:
        session.close()

    # Potentially regenerate the AI preference summary (every SUMMARY_THRESHOLD feedbacks)
    maybe_update_preference_summary()

    return jsonify({'status': 'success'})


@app.route('/health')
def health():
    """
    Scraper health dashboard.

    Shows per-scraper stats for the last 7 days:
    - Last run timestamp and event yield
    - Average events per run
    - Success rate
    - Status badge (Healthy / Warning / Error) based on yield and error rate

    Status logic (evaluated in order):
    1. No runs in last 7 days       -> Warning (No Runs)
    2. Last run raised an exception -> Error
    3. Last run returned 0 events   -> Warning (Empty)
    4. Last run < 50% of average    -> Warning (Low Yield)
    5. Success rate >= 80%          -> Healthy
    6. Success rate >= 50%          -> Warning
    7. Otherwise                    -> Error
    """
    session = Session()
    try:
        active_scrapers   = sorted(SITES.keys(), key=lambda k: SOURCE_NAMES.get(k, k).lower())
        disabled_scrapers = []

        # Event counts per source (total and future)
        from sqlalchemy import case
        event_counts = session.query(
            Event.source,
            func.count(Event.id).label('total'),
            func.sum(case((Event.date >= datetime.now(), 1), else_=0)).label('future'),
        ).group_by(Event.source).all()

        event_stats = {
            row.source: {'total': row.total, 'future': row.future}
            for row in event_counts
        }

        # Scraper run records from the last 7 days
        week_ago    = datetime.utcnow() - timedelta(days=7)
        recent_runs = session.query(ScraperRun).filter(
            ScraperRun.run_timestamp >= week_ago
        ).order_by(ScraperRun.run_timestamp.desc()).all()

        # Compute per-scraper stats dict
        scraper_stats = {}
        for source in active_scrapers + disabled_scrapers:
            runs = [r for r in recent_runs if r.source == source]
            if runs:
                successful_runs = [r for r in runs if r.success]
                last_run        = runs[0]  # Most recent (already sorted desc)

                scraper_stats[source] = {
                    'total_runs':        len(runs),
                    'successful_runs':   len(successful_runs),
                    'success_rate':      (len(successful_runs) / len(runs) * 100),
                    'last_run':          last_run.run_timestamp,
                    'last_success':      last_run.success,
                    'last_events_found': last_run.events_found,
                    'last_events_added': last_run.events_added,
                    'last_duration':     last_run.duration_seconds,
                    'last_error':        last_run.error_message,
                    'avg_events':        sum(r.events_found for r in runs) / len(runs),
                    'avg_duration':      sum(r.duration_seconds for r in runs) / len(runs),
                }
            else:
                # No runs recorded — show zeroes
                scraper_stats[source] = {
                    'total_runs': 0, 'successful_runs': 0, 'success_rate': 0,
                    'last_run': None, 'last_success': None,
                    'last_events_found': 0, 'last_events_added': 0,
                    'last_duration': 0, 'last_error': None,
                    'avg_events': 0, 'avg_duration': 0,
                }

        # Aggregate totals for the summary banner
        total_events        = sum(stats['total']  for stats in event_stats.values())
        total_future        = sum(stats['future'] for stats in event_stats.values())
        total_runs          = len(recent_runs)
        successful_runs     = len([r for r in recent_runs if r.success])
        overall_success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0

        return render_template(
            'health.html',
            active_scrapers=active_scrapers,
            disabled_scrapers=disabled_scrapers,
            event_stats=event_stats,
            scraper_stats=scraper_stats,
            source_names=SOURCE_NAMES,
            total_events=total_events,
            total_future=total_future,
            total_runs=total_runs,
            overall_success_rate=overall_success_rate,
            current_time=phoenix_now(),
        )
    finally:
        session.close()


@app.route('/calendar')
def calendar_view():
    """
    Monthly calendar grid view.

    Query parameters:
        year, month     — Which month to display (defaults to current)
        sources         — Multi-value source filter (same as index)

    Events are grouped by day number and passed to the template as
    events_by_day = {day_int: [Event, ...]}. The template renders a standard
    7-column calendar grid using Python's calendar.monthcalendar().
    """
    session = Session()
    try:
        now = datetime.now()
        try:
            year  = int(request.args.get('year',  now.year))
            month = int(request.args.get('month', now.month))
        except ValueError:
            year, month = now.year, now.month

        # Wrap month boundaries (e.g. month=0 -> December of previous year)
        if month < 1:  month, year = 12, year - 1
        if month > 12: month, year = 1,  year + 1

        selected_sources = request.args.getlist('sources')

        last_day = date(year, month, calendar.monthrange(year, month)[1])

        query = session.query(Event).filter(
            Event.date >= datetime(year, month, 1),
            Event.date <= datetime(year, month, last_day.day, 23, 59, 59),
        )
        if selected_sources:
            query = query.filter(Event.source.in_(selected_sources))

        events = query.order_by(Event.date).all()

        # Group events by calendar day number for the template
        events_by_day = {}
        for ev in events:
            events_by_day.setdefault(ev.date.day, []).append(ev)

        # calendar.monthcalendar returns a list of weeks; each week is 7 ints (0 = padding)
        # setfirstweekday(6) = Sunday, matching the Sun-Mon-...-Sat column headers in the template
        calendar.setfirstweekday(6)
        cal = calendar.monthcalendar(year, month)

        # Compute prev/next month for navigation links
        prev_year,  prev_month = (year - 1, 12) if month == 1  else (year, month - 1)
        next_year,  next_month = (year + 1, 1)  if month == 12 else (year, month + 1)

        raw_sources = [s[0] for s in session.query(Event.source).distinct().all()]
        sources = sorted(raw_sources, key=lambda s: SOURCE_NAMES.get(s, s))

        return render_template(
            'calendar.html',
            year=year, month=month,
            month_name=calendar.month_name[month],
            cal=cal,
            events_by_day=events_by_day,
            sources=sources,
            source_names=SOURCE_NAMES,
            source_colors=SOURCE_COLORS,
            selected_sources=selected_sources,
            prev_year=prev_year, prev_month=prev_month,
            next_year=next_year, next_month=next_month,
            today=date.today(),
            total_events=len(events),
        )
    finally:
        session.close()


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """
    User taste profile page.

    GET  — Display current taste_prompt, AI-generated preference_summary,
           recent feedback history, and summary generation history.
    POST — Save an updated taste_prompt (form field 'taste_prompt').
           Redirects back to GET after saving.
    """
    session = Session()
    try:
        if request.method == 'POST':
            taste_prompt = request.form.get('taste_prompt', '').strip()
            profile_row  = session.query(UserProfile).first()
            if not profile_row:
                profile_row = UserProfile()
                session.add(profile_row)
            profile_row.taste_prompt = taste_prompt
            session.commit()
            return redirect('/profile')

        profile_row     = session.query(UserProfile).first()
        feedback_count  = session.query(FeedbackHistory).count()
        liked_count     = session.query(FeedbackHistory).filter_by(interested=True).count()
        disliked_count  = session.query(FeedbackHistory).filter_by(interested=False).count()

        # Most recent 10 feedback entries for the activity feed
        recent_feedback = session.query(FeedbackHistory).order_by(
            FeedbackHistory.created_at.desc()
        ).limit(10).all()

        # Most recent 10 archived summaries for the history section
        profile_history = session.query(PreferenceProfileHistory).order_by(
            PreferenceProfileHistory.created_at.desc()
        ).limit(10).all()

        return render_template(
            'profile.html',
            profile=profile_row,
            feedback_count=feedback_count,
            liked_count=liked_count,
            disliked_count=disliked_count,
            recent_feedback=recent_feedback,
            profile_history=profile_history,
        )
    finally:
        session.close()


@app.route('/shortlist.ics')
def shortlist_ics():
    """
    Download all pinned (shortlist) future events as an ICS file.

    Google Calendar has no bulk-import URL, so this is the only way to get
    every shortlist event into GCal in one step: import this file via
    Google Calendar → Settings → Import & export → Import.
    """
    session = Session()
    try:
        pinned = session.query(Event).filter(
            Event.pinned == True,
            Event.date >= datetime.now(),
        ).order_by(Event.date).all()

        body = events_to_ics(pinned, calendar_name='Phoenix Events Shortlist')
        return Response(
            body,
            mimetype='text/calendar',
            headers={
                'Content-Disposition': 'attachment; filename="phoenix-events-shortlist.ics"',
            },
        )
    finally:
        session.close()


@app.route('/event/<int:event_id>.ics')
def event_ics(event_id):
    """Download a single event as an ICS file."""
    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return 'Event not found', 404
        body = events_to_ics([event], calendar_name=f'Event: {event.title}')
        # Sanitize filename: keep alphanumerics and dashes only
        safe_title = ''.join(c if c.isalnum() else '-' for c in (event.title or 'event'))[:50]
        return Response(
            body,
            mimetype='text/calendar',
            headers={
                'Content-Disposition': f'attachment; filename="{safe_title}.ics"',
            },
        )
    finally:
        session.close()


@app.route('/pin', methods=['POST'])
def pin():
    """Toggle the pinned/shortlist status of an event. Expects JSON: {"event_id": <int>}"""
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
    
    event_id = data.get('event_id')
    
    # Validate input
    if event_id is None:
        return jsonify({'status': 'error', 'message': 'event_id is required'}), 400
    if not isinstance(event_id, int):
        return jsonify({'status': 'error', 'message': 'event_id must be an integer'}), 400
    
    session = Session()
    try:
        event = session.query(Event).get(event_id)
        if not event:
            return jsonify({'status': 'error', 'message': 'Event not found'}), 404
        event.pinned = not event.pinned
        session.commit()
        pinned = event.pinned
        return jsonify({'status': 'success', 'pinned': pinned})
    finally:
        session.close()


@app.route('/profile/summary', methods=['POST'])
def profile_summary():
    """Save a manually-edited preference_summary."""
    summary = request.form.get('preference_summary', '').strip()
    
    # Validate input length (prevent abuse)
    if len(summary) > 10000:
        return jsonify({'status': 'error', 'message': 'Preference summary too long (max 10000 characters)'}), 400
    
    session = Session()
    try:
        profile_row = session.query(UserProfile).first()
        if not profile_row:
            profile_row = UserProfile()
            session.add(profile_row)
        profile_row.preference_summary = summary
        session.commit()
        return redirect('/profile')
    finally:
        session.close()


@app.route('/llm-usage')
def llm_usage():
    """
    LLM token usage dashboard.

    Renders four sections (template: llm_usage.html):
      1. Today's budget     — Per (key, model) rolling 24h token usage vs TPD,
                              plus "next tick" (when the oldest in-window call
                              rolls off) and "free at" (if currently over limit).
      2. Usage chart        — Stacked line chart of rolling 24h % of TPD over
                              the last 7 days, per model. Non-stacked because
                              percentages of different TPDs can't be summed.
      3. Daily table        — Token usage by day × (key, model) over last 7 days.
      4. All-time totals    — Per model: total calls, tokens, avg tokens/call.
      5. Recent calls log   — Last 100 Groq calls with full details.

    All data is queried fresh from the llm_calls table; rate limits are
    cross-referenced against groq_model_limits.
    """
    session = Session()
    try:
        now      = datetime.utcnow()
        day_ago  = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        # All model limits from DB
        limits = {r.model: r for r in session.query(GroqModelLimit).all()}

        # --- Today's budget usage per (key, model) ---
        budget_rows = session.query(
            LLMCall.api_key_label,
            LLMCall.model,
            func.count(LLMCall.id).label('calls'),
            func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens).label('tokens'),
            func.avg(LLMCall.duration_seconds).label('avg_dur'),
        ).filter(
            LLMCall.timestamp >= day_ago,
            LLMCall.provider == 'groq',
        ).group_by(LLMCall.api_key_label, LLMCall.model).all()

        # For reset-time calculations, fetch the actual calls in the 24h window
        # ordered by timestamp. We use these to compute when the oldest call
        # rolls off (budget tick) and, if over-budget, when usage drops under.
        window_calls = session.query(
            LLMCall.api_key_label,
            LLMCall.model,
            LLMCall.timestamp,
            (LLMCall.prompt_tokens + LLMCall.completion_tokens).label('tokens'),
        ).filter(
            LLMCall.timestamp >= day_ago,
            LLMCall.provider == 'groq',
        ).order_by(LLMCall.timestamp.asc()).all()

        # Group window_calls by (key, model)
        calls_by_pair = {}
        for c in window_calls:
            calls_by_pair.setdefault((c.api_key_label, c.model), []).append(c)

        budget = []
        for r in budget_rows:
            lim = limits.get(r.model)
            tpd = lim.tpd if lim and lim.tpd else None
            tokens_used = r.tokens or 0
            pct = (tokens_used / tpd * 100) if tpd else None

            pair_calls = calls_by_pair.get((r.api_key_label, r.model), [])

            # Next tick: when the oldest call in the window rolls out of the
            # 24h window, freeing up its tokens.
            next_tick_at = None
            next_tick_tokens = 0
            if pair_calls:
                oldest = pair_calls[0]
                next_tick_at = oldest.timestamp + timedelta(hours=24)
                next_tick_tokens = oldest.tokens or 0

            # Free-at: only meaningful if currently over TPD. Iterate through
            # the calls from oldest, subtracting each; the first call whose
            # removal brings usage under TPD is when we become usable again.
            free_at = None
            if tpd and tokens_used >= tpd:
                remaining = tokens_used
                for c in pair_calls:
                    remaining -= (c.tokens or 0)
                    if remaining < tpd:
                        free_at = c.timestamp + timedelta(hours=24)
                        break

            budget.append({
                'key':   r.api_key_label,
                'model': r.model,
                'calls': r.calls,
                'tokens': tokens_used,
                'tpd':   tpd,
                'pct':   pct,
                'avg_dur': r.avg_dur or 0,
                'next_tick_at': next_tick_at,
                'next_tick_tokens': next_tick_tokens,
                'free_at': free_at,
            })
        budget.sort(key=lambda x: (x['key'], x['model']))

        # --- Per-day usage for last 7 days ---
        # SQLite strftime to group by date. We shift the timestamp by -7h so
        # buckets align with Phoenix calendar days; otherwise a 9pm Phoenix
        # call (4am UTC next day) would land in the wrong column.
        daily_rows = session.query(
            func.strftime('%Y-%m-%d', LLMCall.timestamp, '-7 hours').label('day'),
            LLMCall.api_key_label,
            LLMCall.model,
            func.count(LLMCall.id).label('calls'),
            func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens).label('tokens'),
        ).filter(
            LLMCall.timestamp >= week_ago,
            LLMCall.provider == 'groq',
        ).group_by('day', LLMCall.api_key_label, LLMCall.model
        ).order_by('day').all()

        # Collect unique (key, model) combos and days seen
        combos = sorted({(r.api_key_label, r.model) for r in daily_rows})
        days   = sorted({r.day for r in daily_rows})
        daily_lookup = {(r.day, r.api_key_label, r.model): r for r in daily_rows}

        # --- Hourly chart data (last 7 days, per model) ---
        # Query hourly token buckets in Phoenix-local hours, then compute a
        # ROLLING 24h window as a percentage of each model's TPD. This mirrors
        # how the rate limiter actually sees usage (a rolling window, not a
        # calendar day). The -7h SQL shift keeps the bucket keys consistent
        # with the Phoenix-local timeline we build below.
        chart_window_start = now - timedelta(days=8)  # extra day for rolling window warmup
        chart_rows = session.query(
            func.strftime('%Y-%m-%d %H:00', LLMCall.timestamp, '-7 hours').label('hour'),
            LLMCall.model,
            func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens).label('tokens'),
        ).filter(
            LLMCall.timestamp >= chart_window_start,
            LLMCall.provider == 'groq',
        ).group_by('hour', LLMCall.model).order_by('hour').all()

        # Build full hourly timeline (last 7 days) in Phoenix local time so
        # labels and rolling-sum lookups match the -7h SQL buckets above.
        now_phx = now - _PHOENIX_UTC_OFFSET
        timeline = []
        cursor = (now_phx - timedelta(days=7)).replace(minute=0, second=0, microsecond=0)
        end    = now_phx.replace(minute=0, second=0, microsecond=0)
        while cursor <= end:
            timeline.append(cursor)
            cursor += timedelta(hours=1)

        # Bucket raw hourly tokens per model (keys are Phoenix-local hours)
        chart_models = sorted({r.model for r in chart_rows})
        hourly_tokens = {m: {} for m in chart_models}
        for r in chart_rows:
            hourly_tokens[r.model][r.hour] = r.tokens or 0

        # For each hour in timeline, compute rolling 24h sum / TPD * 100
        chart_datasets = []
        for m in chart_models:
            lim = limits.get(m)
            tpd = lim.tpd if lim and lim.tpd else None
            data = []
            for pt in timeline:
                total = 0
                for h in range(24):
                    key = (pt - timedelta(hours=h)).strftime('%Y-%m-%d %H:00')
                    total += hourly_tokens[m].get(key, 0)
                if tpd:
                    data.append(round(total / tpd * 100, 2))
                else:
                    data.append(None)
            chart_datasets.append({'label': m, 'data': data, 'tpd': tpd})

        # Axis labels: "MM-DD HH" in Phoenix local time
        chart_labels = [pt.strftime('%m-%d %H') for pt in timeline]

        # --- Recent calls ---
        recent = session.query(LLMCall).filter(
            LLMCall.provider == 'groq'
        ).order_by(LLMCall.id.desc()).limit(100).all()

        # --- All-time totals per model ---
        totals = session.query(
            LLMCall.model,
            func.count(LLMCall.id).label('calls'),
            func.sum(LLMCall.prompt_tokens + LLMCall.completion_tokens).label('tokens'),
            func.avg(LLMCall.duration_seconds).label('avg_dur'),
        ).filter(LLMCall.provider == 'groq'
        ).group_by(LLMCall.model).order_by(func.count(LLMCall.id).desc()).all()

        # --- 429 audit log (most recent 50) ---
        rate_limit_events = session.query(GroqRateLimitEvent).order_by(
            GroqRateLimitEvent.id.desc()
        ).limit(50).all()

        return render_template(
            'llm_usage.html',
            budget=budget,
            days=days,
            combos=combos,
            daily_lookup=daily_lookup,
            limits=limits,
            recent=recent,
            totals=totals,
            now=now,
            chart_labels=chart_labels,
            chart_datasets=chart_datasets,
            rate_limit_events=rate_limit_events,
        )
    finally:
        session.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true', port=5000)
