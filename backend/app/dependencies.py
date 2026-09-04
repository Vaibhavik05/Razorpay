"""
Application Dependencies
Re-exports commonly used dependencies like get_db for FastAPI routers and tests.
"""
from backend.app.core.database import get_db

__all__ = ["get_db"]
