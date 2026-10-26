from flask import Flask
from app.config import Config
from app.data.extensions import db, login_manager
from app.data.models import Product, Sale, SaleItem, Supplier, User
from app.presentation.routes.main import main_bp
from app.presentation.routes.auth import auth_bp
from app.presentation.routes.supplier import supplier_bp


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(supplier_bp)
    app.register_blueprint(supplier_bp, name="suppliers")

    with app.app_context():
        try:
            Supplier.__table__.create(db.engine, checkfirst=True)
        except Exception:
            pass

    return app
