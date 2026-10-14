from datetime import datetime, timezone
from extensions import db

class Article(db.Model):
    __tablename__ = "articles"
    id = db.Column(db.Integer, primary_key=True)
    title_en = db.Column(db.String(220), nullable=False)
    title_te = db.Column(db.String(220))
    slug = db.Column(db.String(240), unique=True, nullable=False, index=True)
    summary_en = db.Column(db.String(500), nullable=False)
    summary_te = db.Column(db.String(500))
    body_en = db.Column(db.Text, nullable=False)
    body_te = db.Column(db.Text)
    language = db.Column(db.String(8), nullable=False, default="both")
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_name = db.Column(db.String(200))
    source_url = db.Column(db.String(1000))
    image_url = db.Column(db.String(1000))
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    category = db.relationship("Category", back_populates="articles")
    author = db.relationship("User", backref="articles")
