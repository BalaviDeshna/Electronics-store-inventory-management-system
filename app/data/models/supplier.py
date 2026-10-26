from app.data.extensions import db


class Supplier(db.Model):
    """A supplier entity representing a vendor providing products."""

    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    contact_info = db.Column(db.String(255), nullable=True)
    address = db.Column(db.Text, nullable=True)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

    def __init__(self, **kwargs):
        if "contact_information" in kwargs and "contact_info" not in kwargs:
            kwargs["contact_info"] = kwargs.pop("contact_information")
        super().__init__(**kwargs)

    @property
    def contact_information(self):
        """Acceptance criteria compatibility property."""
        return self.contact_info

    @contact_information.setter
    def contact_information(self, value):
        self.contact_info = value

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "contact_info": self.contact_info,
            "contact_information": self.contact_information,
            "address": self.address,
            "email": self.email,
            "phone": self.phone,
        }

    def __repr__(self):
        return f"<Supplier id={self.id} name={self.name!r}>"
