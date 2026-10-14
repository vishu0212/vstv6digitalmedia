from extensions import db

class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name_en = db.Column(db.String(80), unique=True, nullable=False)
    name_te = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    articles = db.relationship("Article", back_populates="category")
