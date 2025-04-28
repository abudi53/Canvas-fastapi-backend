from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str
