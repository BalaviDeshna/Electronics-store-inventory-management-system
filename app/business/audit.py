from app.data.extensions import db
from app.data.models.audit_log import AuditLog


def record_audit(action, entity_type, entity_id, details=None):
    """Add an audit record to the current database transaction."""
    audit_entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.session.add(audit_entry)
    return audit_entry