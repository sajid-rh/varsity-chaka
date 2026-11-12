"""Writes audit log entries. Every administrator action goes through here."""
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit(
    db: Session,
    *,
    actor: User,
    action: str,
    target_type: str,
    target_id: int | None,
    details: dict | None = None,
) -> None:
    """Add an audit row to the session. The caller commits, so the log entry and the
    change it describes are saved together or not at all."""
    db.add(
        AuditLog(
            university_id=actor.university_id,
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
    )
