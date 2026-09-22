"""NYSE calendar shared by the residual screen."""
from functools import lru_cache


@lru_cache(maxsize=1)
def calendar():
    import exchange_calendars as xcals
    return xcals.get_calendar("XNYS", start="2000-01-01", end="2040-12-31")
