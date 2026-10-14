
import logging

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)

from extensions import db
from models.contact_message import ContactMessage

contact_bp = Blueprint("contact", __name__)
logger = logging.getLogger(__name__)


@contact_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    # Validate required fields.
    if not all([name, email, subject, message]):
        flash("Please complete all required fields.", "error")
        return redirect(url_for("contact.contact"))

    # Validate field lengths.
    if len(name) > 100 or len(email) > 254:
        flash("Please check the length of your name and email.", "error")
        return redirect(url_for("contact.contact"))

    if len(subject) > 100 or len(message) > 5000:
        flash("Your subject or message is too long.", "error")
        return redirect(url_for("contact.contact"))

    # Basic email format validation.
    if (
        "@" not in email
        or "." not in email.rsplit("@", 1)[-1]
        or email.startswith("@")
    ):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("contact.contact"))

    # Save the message to MySQL.
    try:
        contact_message = ContactMessage(
            name=name,
            email=email,
            subject=subject,
            message=message,
        )

        db.session.add(contact_message)
        db.session.commit()

    except Exception:
        db.session.rollback()
        logger.exception("Failed to save a contact form submission.")

        flash(
            "We could not save your message. Please try again later.",
            "error",
        )
        return redirect(url_for("contact.contact"))

    flash(
        "Thank you! Your message has been submitted successfully.",
        "success",
    )
    return redirect(url_for("contact.contact"))
