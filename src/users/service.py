import logging
from uuid import UUID
from sqlalchemy.orm import Session
from ..database.core import DbSession
from ..entities.user import User
from ..auth.service import CurrentUser, verify_password, get_password_hash
from .model import UserResponse, PasswordChange
from ..exceptions import AuthenticationError, BadRequestError


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Fetches a user from the database by their UUID."""
    return db.query(User).filter(User.id == user_id).first()


def get_current_user_details(
    current_user_token: CurrentUser, db: DbSession
) -> UserResponse:
    """
    Retrieves the details for the currently authenticated user.
    """
    user_id = current_user_token.get_uuid()
    if not user_id:
        # This should technically not happen if CurrentUser dependency works
        logging.error(
            "Could not extract user_id from token in get_current_user_details"
        )
        raise AuthenticationError("Invalid token data.")

    user = get_user_by_id(db, user_id)
    if not user:
        # This might happen if the user was deleted after the token was issued
        logging.warning(
            f"User with ID {user_id} not found in database, but token was valid."
        )
        raise AuthenticationError("User not found.")

    # Use model_validate instead of the deprecated from_orm
    return UserResponse.model_validate(user)


def change_user_password(
    current_user_token: CurrentUser, db: DbSession, password_change: PasswordChange
) -> None:
    """
    Allows the currently authenticated user to change their password.
    """
    user_id = current_user_token.get_uuid()
    if not user_id:
        logging.error("Could not extract user_id from token in change_user_password")
        raise AuthenticationError("Invalid token data.")

    user = get_user_by_id(db, user_id)
    if not user:
        logging.warning(f"User with ID {user_id} not found for password change.")
        raise AuthenticationError("User not found.")

    # Verify current password
    if not verify_password(password_change.current_password, user.hashed_password):  # type: ignore
        logging.warning(
            f"Incorrect current password attempt for user {user.username} (ID: {user_id})."
        )
        raise BadRequestError("Incorrect current password.")

    # Check if new passwords match
    if password_change.new_password != password_change.new_password_confirm:
        raise BadRequestError("New passwords do not match.")

    # Update password
    try:
        user.hashed_password = get_password_hash(password_change.new_password)  # type: ignore
        db.add(user)
        db.commit()
        logging.info(
            f"Password successfully changed for user {user.username} (ID: {user_id})."
        )
    except Exception as e:
        db.rollback()
        logging.error(
            f"Database error changing password for user {user.username} (ID: {user_id}): {e}"
        )
        raise  # Re-raise the exception after logging
