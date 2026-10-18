from datetime import datetime, timezone

from extensions import db


class RssRun(db.Model):
    __tablename__ = "rss_runs"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    finished_at = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(
        db.String(32), nullable=False, default="running", index=True
    )
    feeds_checked = db.Column(db.Integer, nullable=False, default=0)
    created = db.Column(db.Integer, nullable=False, default=0)
    duplicates = db.Column(db.Integer, nullable=False, default=0)
    updated = db.Column(db.Integer, nullable=False, default=0)
    skipped = db.Column(db.Integer, nullable=False, default=0)
    errors = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
