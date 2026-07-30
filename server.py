"""ASGI-Einstiegspunkt für uvicorn: `uvicorn server:app --reload`."""

from codementor.api.app import app as app

__all__ = ["app"]
