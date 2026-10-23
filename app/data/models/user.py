from flask_login import UserMixin
from app.data.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(80), unique=True, nullable=False, index=True
    )
    password_hash = db.Column(db.String(60), nullable=False)

    def set_password(self, password):
        from app.business.security import hash_password
        self.password_hash = hash_password(password)

    def check_password(self, password):
        from app.business.security import verify_password
        return verify_password(password, self.password_hash)