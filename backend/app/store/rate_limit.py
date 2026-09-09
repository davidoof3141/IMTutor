"""Shared fixed-window rate limiting.

Backs the abuse protection on the unauthenticated auth endpoints. Kept in
app/store (not app/core) for the same reason as the rest of auth: it is I/O
and not part of the deterministic control layer.
"""

from app.store.db import Conn


class RateLimitRepository:
    def __init__(self, conn: Conn) -> None:
        self._conn = conn

    def hit(self, bucket: str, *, limit: int, window_seconds: int) -> bool:
        """Record one request against `bucket` and report whether the caller
        has now exceeded `limit` within the current `window_seconds` window.

        The window resets lazily: a hit that lands after the current window
        has aged out starts a fresh one at count 1.
        """
        row = self._conn.execute(
            """
            INSERT INTO rate_limits (bucket, window_start, count)
            VALUES (%(bucket)s, now(), 1)
            ON CONFLICT (bucket) DO UPDATE SET
                count = CASE
                    WHEN rate_limits.window_start
                         < now() - make_interval(secs => %(window)s)
                    THEN 1
                    ELSE rate_limits.count + 1
                END,
                window_start = CASE
                    WHEN rate_limits.window_start
                         < now() - make_interval(secs => %(window)s)
                    THEN now()
                    ELSE rate_limits.window_start
                END
            RETURNING count
            """,
            {"bucket": bucket, "window": window_seconds},
        ).fetchone()
        self._conn.commit()
        assert row is not None
        return int(row["count"]) > limit
