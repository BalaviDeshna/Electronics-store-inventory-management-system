from flask_login import current_user

from app.data.extensions import db
from app.data.models.audit_log import AuditLog


def record_audit(action, entity_type, entity_id, details=None):
    """Add an audit record for the authenticated actor to the current transaction."""
    actor_id = current_user.id if current_user.is_authenticated else None

    audit_entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        user_id=actor_id,
    )
    db.session.add(audit_entry)
    return audit_entry
