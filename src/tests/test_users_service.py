import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from src.users import service as users_service
from src.users.model import UserResponse, PasswordChange
from src.entities.user import User
from src.auth.model import TokenData
from src.exceptions import AuthenticationError, BadRequestError


# Fixtures
@pytest.fixture
def mock_db_session():
    """Provides a mocked SQLAlchemy Session."""
    return MagicMock(spec=Session)


@pytest.fixture
def test_user_id() -> UUID:
    """Provides a consistent UUID for testing."""
    return uuid4()


@pytest.fixture
def test_user(test_user_id) -> User:
    """Provides a sample User entity."""
    return User(
        id=test_user_id,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed_password_example",  # Use a placeholder or generate one if needed
        is_active=True,
    )


@pytest.fixture
def current_user_token(test_user_id) -> TokenData:
    """Provides a sample TokenData representing the current user."""
    return TokenData(user_id=str(test_user_id))


# Tests for get_user_by_id
def test_get_user_by_id_found(mock_db_session, test_user, test_user_id):
    """Tests retrieving a user that exists."""
    mock_query = mock_db_session.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = test_user

    user = users_service.get_user_by_id(mock_db_session, test_user_id)

    mock_db_session.query.assert_called_once_with(User)
    mock_query.filter.assert_called_once()  # Check filter condition if needed
    mock_filter.first.assert_called_once()
    assert user == test_user


def test_get_user_by_id_not_found(mock_db_session, test_user_id):
    """Tests retrieving a user that does not exist."""
    mock_query = mock_db_session.query.return_value
    mock_filter = mock_query.filter.return_value
    mock_filter.first.return_value = None

    user = users_service.get_user_by_id(mock_db_session, test_user_id)

    mock_db_session.query.assert_called_once_with(User)
    mock_query.filter.assert_called_once()
    mock_filter.first.assert_called_once()
    assert user is None


# Tests for get_current_user_details
@patch("src.users.service.get_user_by_id")
def test_get_current_user_details_success(
    mock_get_user, mock_db_session, current_user_token, test_user, test_user_id
):
    """Tests retrieving details for the current user successfully."""
    mock_get_user.return_value = test_user

    user_response = users_service.get_current_user_details(
        current_user_token, mock_db_session
    )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    assert isinstance(user_response, UserResponse)
    assert user_response.id == test_user_id
    assert user_response.username == test_user.username
    assert user_response.email == test_user.email


@patch("src.users.service.get_user_by_id")
def test_get_current_user_details_user_not_found(
    mock_get_user, mock_db_session, current_user_token, test_user_id
):
    """Tests retrieving details when the user ID from token is not found in DB."""
    mock_get_user.return_value = None

    with pytest.raises(AuthenticationError, match="User not found."):
        users_service.get_current_user_details(current_user_token, mock_db_session)

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)


def test_get_current_user_details_invalid_token(mock_db_session):
    """Tests retrieving details with a token missing the user_id."""
    with pytest.raises(AuthenticationError, match="Invalid token data."):
        # Pass None for user_id to trigger the error path
        invalid_token_mock = MagicMock(spec=TokenData)
        invalid_token_mock.get_uuid.return_value = None
        users_service.get_current_user_details(invalid_token_mock, mock_db_session)


# Tests for change_user_password
@patch("src.users.service.get_user_by_id")
@patch("src.users.service.verify_password")
@patch("src.users.service.get_password_hash")
def test_change_user_password_success(
    mock_get_hash,
    mock_verify_pw,
    mock_get_user,
    mock_db_session,
    current_user_token,
    test_user,
    test_user_id,
):
    """Tests changing the user password successfully."""
    mock_get_user.return_value = test_user
    mock_verify_pw.return_value = True
    mock_get_hash.return_value = "hashed_password_example"

    password_change_data = PasswordChange(
        current_password="old_password",
        new_password="new_password",
        new_password_confirm="new_password",
    )

    users_service.change_user_password(
        current_user_token, mock_db_session, password_change_data
    )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    mock_verify_pw.assert_called_once_with("old_password", test_user.hashed_password)
    mock_get_hash.assert_called_once_with("new_password")
    mock_db_session.add.assert_called_once_with(test_user)
    mock_db_session.commit.assert_called_once()
    mock_db_session.rollback.assert_not_called()
    assert test_user.hashed_password == "hashed_password_example"


@patch("src.users.service.get_user_by_id")
def test_change_user_password_user_not_found(
    mock_get_user, mock_db_session, current_user_token, test_user_id
):
    """Tests changing password when the user is not found."""
    mock_get_user.return_value = None
    password_change_data = PasswordChange(
        current_password="old", new_password="new", new_password_confirm="new"
    )

    with pytest.raises(AuthenticationError, match="User not found."):
        users_service.change_user_password(
            current_user_token, mock_db_session, password_change_data
        )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@patch("src.users.service.get_user_by_id")
@patch("src.users.service.verify_password")
def test_change_user_password_incorrect_current(
    mock_verify_pw,
    mock_get_user,
    mock_db_session,
    current_user_token,
    test_user,
    test_user_id,
):
    """Tests changing password with incorrect current password."""
    mock_get_user.return_value = test_user
    mock_verify_pw.return_value = False  # Simulate incorrect password
    password_change_data = PasswordChange(
        current_password="wrong_old", new_password="new", new_password_confirm="new"
    )

    with pytest.raises(BadRequestError, match="Incorrect current password."):
        users_service.change_user_password(
            current_user_token, mock_db_session, password_change_data
        )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    mock_verify_pw.assert_called_once_with("wrong_old", test_user.hashed_password)
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@patch("src.users.service.get_user_by_id")
@patch("src.users.service.verify_password")
def test_change_user_password_mismatch_new(
    mock_verify_pw,
    mock_get_user,
    mock_db_session,
    current_user_token,
    test_user,
    test_user_id,
):
    """Tests changing password when new passwords don't match."""
    mock_get_user.return_value = test_user
    mock_verify_pw.return_value = True  # Current password is correct
    password_change_data = PasswordChange(
        current_password="old", new_password="new1", new_password_confirm="new2"
    )  # Mismatch

    with pytest.raises(BadRequestError, match="New passwords do not match."):
        users_service.change_user_password(
            current_user_token, mock_db_session, password_change_data
        )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    mock_verify_pw.assert_called_once_with("old", test_user.hashed_password)
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@patch("src.users.service.get_user_by_id")
@patch("src.users.service.verify_password")
@patch("src.users.service.get_password_hash")
def test_change_user_password_db_error(
    mock_get_hash,
    mock_verify_pw,
    mock_get_user,
    mock_db_session,
    current_user_token,
    test_user,
    test_user_id,
):
    """Tests password change when a database error occurs during commit."""
    mock_get_user.return_value = test_user
    mock_verify_pw.return_value = True
    mock_get_hash.return_value = "hashed_password_example"
    mock_db_session.commit.side_effect = Exception(
        "DB commit error"
    )  # Simulate DB error

    password_change_data = PasswordChange(
        current_password="old_password",
        new_password="new_password",
        new_password_confirm="new_password",
    )

    with pytest.raises(Exception, match="DB commit error"):
        users_service.change_user_password(
            current_user_token, mock_db_session, password_change_data
        )

    mock_get_user.assert_called_once_with(mock_db_session, test_user_id)
    mock_verify_pw.assert_called_once_with("old_password", test_user.hashed_password)
    mock_get_hash.assert_called_once_with("new_password")
    mock_db_session.add.assert_called_once_with(test_user)
    mock_db_session.commit.assert_called_once()
    mock_db_session.rollback.assert_called_once()  # Ensure rollback was called
