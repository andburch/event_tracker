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

from flask import Flask, render_template, request, jsonify, redirect
import sys
import os

# Add project root to path so imports work when running from the server/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import (
    Session, Event, FeedbackHistory, UserProfile,
    PreferenceProfileHistory, ScraperRun,
)
from recommender.llm_filter import score_events, get_profile, maybe_update_preference_summary
from datetime import datetime, timedelta, date
import calendar
from sqlalchemy import func
from scrapers import SCRAPERS, DISABLED_SCRAPERS

app = Flask(__name__)

from sources import SOURCE_NAMES, SOURCE_COLORS


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

    # Build source list sorted alphabetically by display name for the filter dropdown
    raw_sources = [s[0] for s in session.query(Event.source).distinct().all()]
    sources = sorted(raw_sources, key=lambda s: SOURCE_NAMES.get(s, s))

    session.close()

    # Attach cached scores and sort
    scored_events = score_events(events)
    if sort_by == 'score':
        scored_events.sort(key=lambda x: x[1], reverse=True)
    else:
        scored_events.sort(key=lambda x: x[0].date)

    return render_template(
        'index.html',
        events=scored_events,
        sources=sources,
        source_names=SOURCE_NAMES,
        selected_sources=selected_sources,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
    )


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
    data       = request.json
    event_id   = data.get('event_id')
    interested = data.get('interested')

    session = Session()
    event = session.query(Event).get(event_id)
    if not event:
        session.close()
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

    active_scrapers   = [s.source_name for s in SCRAPERS]
    disabled_scrapers = [s.source_name for s in DISABLED_SCRAPERS]

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

    session.close()

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
        current_time=datetime.now(),
    )


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
    cal = calendar.monthcalendar(year, month)

    # Compute prev/next month for navigation links
    prev_year,  prev_month = (year - 1, 12) if month == 1  else (year, month - 1)
    next_year,  next_month = (year + 1, 1)  if month == 12 else (year, month + 1)

    raw_sources = [s[0] for s in session.query(Event.source).distinct().all()]
    sources = sorted(raw_sources, key=lambda s: SOURCE_NAMES.get(s, s))
    session.close()

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

    if request.method == 'POST':
        taste_prompt = request.form.get('taste_prompt', '').strip()
        profile_row  = session.query(UserProfile).first()
        if not profile_row:
            profile_row = UserProfile()
            session.add(profile_row)
        profile_row.taste_prompt = taste_prompt
        session.commit()
        session.close()
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

    session.close()

    return render_template(
        'profile.html',
        profile=profile_row,
        feedback_count=feedback_count,
        liked_count=liked_count,
        disliked_count=disliked_count,
        recent_feedback=recent_feedback,
        profile_history=profile_history,
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
