from fastapi import APIRouter, HTTPException, status
from ..database.core import DbSession
from ..auth.service import CurrentUser
from . import service
from . import model
from ..exceptions import AuthenticationError, BadRequestError

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=model.UserResponse)
def read_users_me(current_user: CurrentUser, db: DbSession):
    """Retrieves the details of the currently authenticated user."""
    try:
        return service.get_current_user_details(current_user_token=current_user, db=db)
    except AuthenticationError as e:
        # This might happen if the user was deleted after token issuance
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def update_user_password(
    password_change: model.PasswordChange,
    current_user: CurrentUser,
    db: DbSession,
):
    """Allows the currently authenticated user to change their password."""
    try:
        service.change_user_password(
            current_user_token=current_user, db=db, password_change=password_change
        )
        return None  # Return None for 204 No Content
    except AuthenticationError as e:
        # Should not happen if CurrentUser dependency works, but handle defensively
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        # Catch-all for unexpected errors (like database issues during commit)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while changing the password.",
        )
