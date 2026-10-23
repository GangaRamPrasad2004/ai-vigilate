import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class Session(BaseModel):
    session_id: str
    user_id: str = "fin-ops-user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: Dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, max_age_minutes: int = 15) -> bool:
        now = datetime.now(timezone.utc)
        return (now - self.last_accessed_at) > timedelta(minutes=max_age_minutes)


class SessionStore:
    """
    In-memory isolated volatile session store.
    Strictly decouples volatile session state from durable governance policy.
    """
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create_session(self, user_id: str = "fin-ops-user", custom_id: Optional[str] = None) -> Session:
        session_id = custom_id or f"sess-{uuid.uuid4().hex[:12]}"
        sess = Session(session_id=session_id, user_id=user_id)
        self._sessions[session_id] = sess
        return sess

    def get_session(self, session_id: str) -> Optional[Session]:
        sess = self._sessions.get(session_id)
        if sess:
            sess.last_accessed_at = datetime.now(timezone.utc)
        return sess

    def store_state(self, session_id: str, key: str, value: Any) -> None:
        sess = self.get_session(session_id)
        if sess is None:
            sess = self.create_session(custom_id=session_id)
        sess.state[key] = value

    def get_state(self, session_id: str, key: str, default: Any = None) -> Any:
        sess = self.get_session(session_id)
        if sess is None:
            return default
        return sess.state.get(key, default)

    def expire_old_sessions(self, max_age_minutes: int = 15) -> int:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired(max_age_minutes)]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def clear(self) -> None:
        self._sessions.clear()


# Global session store instance
session_store = SessionStore()
