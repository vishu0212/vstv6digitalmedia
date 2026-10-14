
import logging

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)

contact_bp = Blueprint("contact", __name__)
logger = logging.getLogger(__name__)


@contact_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not all([name, email, subject, message]):
        flash("Please complete all required fields.", "error")
        return redirect(url_for("contact.contact"))

    if len(name) > 100 or len(email) > 254:
        flash("Please check the length of your name and email.", "error")
        return redirect(url_for("contact.contact"))

    if len(subject) > 100 or len(message) > 5000:
        flash("Your subject or message is too long.", "error")
        return redirect(url_for("contact.contact"))

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("contact.contact"))

    # Log that a submission was received, without logging personal details.
    logger.info("A newsroom contact form submission was received.")

    # This route validates the submission but does not send an email
    # or save the message to a database yet.
    flash(
        "Your message was received by the application. "
        "Email delivery has not been configured yet.",
        "success",
    )
    return redirect(url_for("contact.contact"))
