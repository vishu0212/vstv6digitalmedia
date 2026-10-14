
from getpass import getpass
from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from models import User


def create_staff():
    email = input("Enter staff email: ").strip().lower()
    display_name = input("Enter staff display name: ").strip()
    password = getpass("Create staff password: ")

    if not email or not display_name or not password:
        print("Error: All fields are required.")
        return

    with app.app_context():
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            print("An account with this email already exists.")
            return

        user = User(
            email=email,
            display_name=display_name,
            password_hash=generate_password_hash(password),
            role="admin",
            active=True
        )

        db.session.add(user)
        db.session.commit()

        print("Staff account created successfully!")
        print(f"Email: {email}")
        print("Password: saved as a secure hash.")


if __name__ == "__main__":
    create_staff()
