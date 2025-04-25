import os
from uuid import UUID, uuid4
from fastapi import Depends
from typing import Annotated
from datetime import datetime, timedelta, timezone
import jwt
from jwt import PyJWTError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from . import model
from src.entities.user import User
from ..exceptions import AuthenticationError
import logging


load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return bcrypt_context.hash(password)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logging.warning(f"User {username} not found")
        return None
    if not verify_password(password, user.hashed_password):  # type: ignore
        logging.warning(f"Password verification failed for user {username}")
        return None
    return user


def create_access_token(email: str, user_id: UUID, expires_delta: timedelta) -> str:
    encode = {
        "sub": email,
        "user_id": str(user_id),
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)  # type: ignore


def verify_token(token: str) -> model.TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])  # type: ignore
        user_id: str = payload.get("user_id")
        return model.TokenData(user_id=user_id)
    except PyJWTError as e:
        logging.warning(f"Token verification failed: {e}")
        raise AuthenticationError()


def register_user(
    db: Session, register_user_request: model.RegisterUserRequest
) -> None:
    try:
        db_user = User(
            id=uuid4(),
            username=register_user_request.username,
            email=register_user_request.email,
            hashed_password=get_password_hash(register_user_request.password),
        )
        db.add(db_user)
        db.commit()
    except Exception as e:
        logging.error(
            f"Error registering user: {register_user_request.username}. Error: {e}"
        )
        raise


def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]) -> model.TokenData:
    return verify_token(token)


CurrentUser = Annotated[model.TokenData, Depends(get_current_user)]


def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session
) -> model.Token:
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logging.warning(f"Authentication failed for user {form_data.username}")
        raise AuthenticationError()
    token = create_access_token(
        email=user.email,  # type: ignore
        user_id=user.id,  # type: ignore
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return model.Token(access_token=token, token_type="bearer")
