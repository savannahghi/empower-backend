"""Hanlde sessions."""
# ussd/session_manager.py

from typing import Any, Dict

from django.core.cache import cache


class SessionManager:
    """Manage sessions using Redis cache."""

    DEFAULT_TIMEOUT = 900  # 15 minutes

    @staticmethod
    def get_session(session_id: str) -> Dict[str, Any]:
        """Retrieve session data from Redis."""
        return cache.get(session_id, {})

    @staticmethod
    def save_session(
        session_id: str, data: Dict[str, Any], timeout: int = DEFAULT_TIMEOUT
    ) -> None:
        """Save session data to Redis."""
        cache.set(session_id, data, timeout)

    @staticmethod
    def delete_session(session_id: str) -> None:
        """Delete session data from Redis."""
        cache.delete(session_id)
