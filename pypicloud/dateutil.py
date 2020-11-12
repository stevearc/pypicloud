import datetime


class _UTC(datetime.tzinfo):
    def dst(self, dt):
        return datetime.timedelta(0)

    def fromutc(self, dt):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self)
        return super().fromutc(dt)

    def tzname(self, dt):
        return "UTC"

    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def __repr__(self):
        return "<UTC>"

    def __str__(self):
        return "UTC"


UTC = _UTC()


def utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow().replace(tzinfo=UTC)


def utcfromtimestamp(t: float) -> datetime.datetime:
    return datetime.datetime.utcfromtimestamp(t).replace(tzinfo=UTC)
