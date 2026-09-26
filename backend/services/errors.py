"""The one exception a service raises to refuse a request.

Services must not import FastAPI; main.py maps ServiceError to an HTTP
response `{"detail": ...}` with `status`, so routers need no try/except.
"""


class ServiceError(Exception):
    """A refused request. `status` is the HTTP code, `detail` the sentence shown."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail
