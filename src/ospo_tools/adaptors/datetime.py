"""Here we collect a set of datetime wrappers and adaptors to be easily replaced during testing and debugging."""

from datetime import datetime
import pytz


def get_datetime_now() -> datetime:
    return datetime.now(pytz.UTC)
