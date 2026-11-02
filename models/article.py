
import re
from datetime import datetime, timezone

from extensions import db

TELUGU_SCRIPT_RE = re.compile(r"[\u0C00-\u0C7F]")
ENGLISH_LETTER_RE = re.compile(r"[A-Za-z]")


def contains_telugu_script(text):
    """Return whether text contains at least one Telugu-script character."""
    return bool(text and TELUGU_SCRIPT_RE.search(text))


def is_telugu_summary(text):
    """Return whether a summary has Telugu text and no English letters."""
    return contains_telugu_script(text) and not ENGLISH_LETTER_RE.search(text)


def utc_now():
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


class Article(db.Model):
    __tablename__ = "articles"

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Titles
    title_en = db.Column(db.String(220))
    title_te = db.Column(db.String(220))

    # URL slug
    slug = db.Column(
        db.String(240),
        unique=True,
        nullable=False,
        index=True,
    )

    # Summaries
    summary_en = db.Column(db.String(500))
    summary_te = db.Column(db.String(500))

    # Full article content
    body_en = db.Column(db.Text)
    body_te = db.Column(db.Text)

    # Language: en, te, or both
    language = db.Column(
        db.String(8),
        nullable=False,
        default="both",
    )

    # Category and author
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        nullable=False,
        index=True,
    )

    author_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Original source information
    source_name = db.Column(db.String(200))
    source_url = db.Column(db.String(1000), index=True)
    image_url = db.Column(db.String(1000))

    # Publication status
    status = db.Column(
        db.String(20),
        nullable=False,
        default="draft",
        index=True,
    )

    # Dates
    published_at = db.Column(
        db.DateTime(timezone=True),
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    category = db.relationship(
        "Category",
        back_populates="articles",
    )

    author = db.relationship(
        "User",
        backref="articles",
    )

    def __repr__(self):
        return (
            f"<Article id={self.id} "
            f"title={self.title_en!r} "
            f"status={self.status!r}>"
        )

    @property
    def display_title(self):
        """Return the Telugu title when available."""
        return self.title_te or self.title_en or ""

    @property
    def display_summary(self):
        """Return the Telugu summary when available."""
        return self.summary_te or self.summary_en or ""

    @property
    def display_body(self):
        """Return the Telugu body when available."""
        return self.body_te or self.body_en or ""

    @property
    def telugu_summary(self):
        """Return the summary only when it has Telugu and no English letters."""
        if is_telugu_summary(self.summary_te):
            return self.summary_te
        return None

    @property
    def telugu_body(self):
        """Return the body when it contains Telugu script."""
        if contains_telugu_script(self.body_te):
            return self.body_te
        return None

    @property
    def telugu_title(self):
        """Return the title when it contains Telugu script."""
        if contains_telugu_script(self.title_te):
            return self.title_te
        return None

    @property
    def telugu_author_name(self):
        """Return the author name when it contains Telugu script."""
        name = self.author.display_name if self.author else None
        return name if contains_telugu_script(name) else None

    @property
    def telugu_category_name(self):
        """Return the category name when it contains Telugu script."""
        name = self.category.name_te if self.category else None
        return name if contains_telugu_script(name) else None

    @property
    def has_telugu_story(self):
        """Check that the public headline and full body contain Telugu."""
        return bool(self.telugu_title and self.telugu_body)

    @property
    def is_published(self):
        """Check whether the article is published."""
        return self.status == "published"
