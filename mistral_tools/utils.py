"""Miscellaneous utility functions and classes"""
import time

class RateLimiter():
    """A simple rate limiter that sleeps for a given amount of time between calls

    usage example:

    .. code-block:: python

        rate_limiter = RateLimiter(1.0)

        for _ in range(10):
            with rate_limiter:
                print("doing something, waiting at least 1 second between calls")

    """
    rate_limit: float
    last_call_time: float|None

    def __init__(self, rate_limit):
        self.rate_limit = rate_limit
        self.last_call_time = None

    def __call__(self):
        """Allows using ``with rate_limiter():`` instead of ``with rate_limiter:``"""
        return self

    def __enter__(self):
        """Sleeps for the remaining time to reach the rate limit"""
        if self.last_call_time is not None:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)

    def __exit__(self, *_):
        """Updates the last call time"""
        self.last_call_time = time.time()
