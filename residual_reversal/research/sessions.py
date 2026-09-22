"""Shared US session boundary; completed bars only, with a publication grace period."""
from datetime import timedelta
from functools import lru_cache
from research.calendar import calendar


@lru_cache(maxsize=2048)
def session_close(day):
    try:
        return calendar().session_close(str(day)).to_pydatetime()
    except (ValueError, KeyError):
        return None


def complete(day, cutoff):
    close = session_close(day)
    return close is not None and close + timedelta(minutes=15) <= cutoff


def latest_complete(cutoff):
    days = calendar().sessions_in_range((cutoff-timedelta(days=14)).date().isoformat(), cutoff.date().isoformat())
    return next(d.date() for d in reversed(days) if complete(d.date(), cutoff))


def target_session(cutoff):
    cal = calendar()
    days = cal.sessions_in_range(cutoff.date().isoformat(), (cutoff+timedelta(days=10)).date().isoformat())
    return next(d.date() for d in days if cal.session_close(d).to_pydatetime() > cutoff)


def contiguous(dates):
    return bool(dates) and list(calendar().sessions_in_range(str(dates[0]), str(dates[-1])).date) == dates
