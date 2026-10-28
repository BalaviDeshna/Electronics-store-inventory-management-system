from datetime import datetime, timezone

from app.data.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(100), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(500), nullable=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", backref="audit_logs")
