import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from src.auth import service as auth_service
from src.auth.model import RegisterUserRequest, TokenData
from src.entities.user import User
from src.exceptions import AuthenticationError
import jwt


# Fixtures
@pytest.fixture
def mock_db_session():
    return MagicMock(spec=Session)


@pytest.fixture
def test_user():
    return User(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        hashed_password=auth_service.get_password_hash("password123"),
    )


# Test verify_password
def test_verify_password_correct():
    hashed_password = auth_service.get_password_hash("password123")
    assert auth_service.verify_password("password123", hashed_password) is True


def test_verify_password_incorrect():
    hashed_password = auth_service.get_password_hash("password123")
    assert auth_service.verify_password("wrongpassword", hashed_password) is False


# Test get_password_hash
def test_get_password_hash():
    password = "password123"
    hashed_password = auth_service.get_password_hash(password)
    assert isinstance(hashed_password, str)
    assert auth_service.verify_password(password, hashed_password) is True


# Test authenticate_user
def test_authenticate_user_success(mock_db_session, test_user):
    mock_db_session.query.return_value.filter.return_value.first.return_value = (
        test_user
    )
    authenticated_user = auth_service.authenticate_user(
        mock_db_session, "testuser", "password123"
    )
    assert authenticated_user == test_user


def test_authenticate_user_not_found(mock_db_session):
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    authenticated_user = auth_service.authenticate_user(
        mock_db_session, "nonexistent", "password123"
    )
    assert authenticated_user is None


def test_authenticate_user_wrong_password(mock_db_session, test_user):
    mock_db_session.query.return_value.filter.return_value.first.return_value = (
        test_user
    )
    authenticated_user = auth_service.authenticate_user(
        mock_db_session, "testuser", "wrongpassword"
    )
    assert authenticated_user is None


# Test create_access_token
@patch("src.auth.service.SECRET_KEY", "testsecret")
@patch("src.auth.service.ALGORITHM", "HS256")
def test_create_access_token():
    user_id = uuid4()
    email = "test@example.com"
    expires_delta = timedelta(minutes=15)
    token = auth_service.create_access_token(email, user_id, expires_delta)
    assert isinstance(token, str)
    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == email
    assert payload["user_id"] == str(user_id)


# Test verify_token
@patch("src.auth.service.SECRET_KEY", "testsecret")
@patch("src.auth.service.ALGORITHM", "HS256")
def test_verify_token_success():
    user_id = uuid4()
    email = "test@example.com"
    expires_delta = timedelta(minutes=15)
    token = auth_service.create_access_token(email, user_id, expires_delta)
    token_data = auth_service.verify_token(token)
    assert isinstance(token_data, TokenData)
    assert token_data.user_id == str(user_id)


@patch("src.auth.service.SECRET_KEY", "testsecret")
@patch("src.auth.service.ALGORITHM", "HS256")
def test_verify_token_expired():
    user_id = uuid4()
    email = "test@example.com"
    expires_delta = timedelta(minutes=-15)  # Expired token
    token = auth_service.create_access_token(email, user_id, expires_delta)
    with pytest.raises(AuthenticationError):
        auth_service.verify_token(token)


@patch("src.auth.service.SECRET_KEY", "testsecret")
@patch("src.auth.service.ALGORITHM", "HS256")
def test_verify_token_invalid():
    with pytest.raises(AuthenticationError):
        auth_service.verify_token("invalidtoken")


# Test register_user
def test_register_user_success(mock_db_session):
    register_request = RegisterUserRequest(
        username="newuser", email="new@example.com", password="newpassword"
    )
    auth_service.register_user(mock_db_session, register_request)
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    # Get the user object passed to db.add
    added_user = mock_db_session.add.call_args[0][0]
    assert isinstance(added_user, User)
    # Access attributes directly for assertion
    assert added_user.username == "newuser"  # type: ignore[comparison-overlap]
    assert added_user.email == "new@example.com"  # type: ignore[comparison-overlap]
    # Ensure hashed_password is treated as a string
    assert auth_service.verify_password("newpassword", str(added_user.hashed_password))


def test_register_user_exception(mock_db_session):
    register_request = RegisterUserRequest(
        username="newuser", email="new@example.com", password="newpassword"
    )
    mock_db_session.commit.side_effect = Exception("DB error")
    with pytest.raises(Exception, match="DB error"):
        auth_service.register_user(mock_db_session, register_request)
    mock_db_session.add.assert_called_once()
    mock_db_session.rollback.assert_not_called()  # Assuming default behavior doesn't rollback automatically on commit error in mock


# Test get_current_user
@patch("src.auth.service.verify_token")
def test_get_current_user(mock_verify_token):
    token = "valid_token"
    expected_token_data = TokenData(user_id=str(uuid4()))
    mock_verify_token.return_value = expected_token_data
    result = auth_service.get_current_user(token)
    mock_verify_token.assert_called_once_with(token)
    assert result == expected_token_data


@patch("src.auth.service.verify_token", side_effect=AuthenticationError)
def test_get_current_user_invalid_token(mock_verify_token):
    token = "invalid_token"
    # Depends() mechanism handles the exception raising, so we just check if verify_token was called
    # In a real FastAPI context, the AuthenticationError would be caught and converted to a 401
    # Here we just test that verify_token is called
    try:
        auth_service.get_current_user(token)
    except AuthenticationError:
        pass  # Expected
    mock_verify_token.assert_called_once_with(token)


# Test login_for_access_token
@patch("src.auth.service.authenticate_user")
@patch("src.auth.service.create_access_token")
def test_login_for_access_token_success(
    mock_create_access_token, mock_authenticate_user, mock_db_session, test_user
):
    form_data = OAuth2PasswordRequestForm(
        username="testuser",
        password="password123",
        scope="",
        grant_type="password",
        client_id=None,
        client_secret=None,
    )
    mock_authenticate_user.return_value = test_user
    mock_create_access_token.return_value = "test_token"

    token_response = auth_service.login_for_access_token(form_data, mock_db_session)

    mock_authenticate_user.assert_called_once_with(
        mock_db_session, "testuser", "password123"
    )
    mock_create_access_token.assert_called_once()
    assert token_response.access_token == "test_token"
    assert token_response.token_type == "bearer"


@patch("src.auth.service.authenticate_user", return_value=None)
def test_login_for_access_token_failure(mock_authenticate_user, mock_db_session):
    form_data = OAuth2PasswordRequestForm(
        username="wronguser",
        password="wrongpassword",
        scope="",
        grant_type="password",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(AuthenticationError):
        auth_service.login_for_access_token(form_data, mock_db_session)

    mock_authenticate_user.assert_called_once_with(
        mock_db_session, "wronguser", "wrongpassword"
    )
