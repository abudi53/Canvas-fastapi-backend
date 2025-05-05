from fastapi import APIRouter, HTTPException, Request
from .service import generate_image_service, save_user_image
from .model import ImageResponse, SaveImageRequest
from ..auth.service import CurrentUser
from ..database.core import DbSession
from ..entities.image import Image
import logging
from ..rate_limiting import limiter


router = APIRouter(prefix="/image", tags=["Image"])


@router.get("/generate", response_model=str)
@limiter.limit("20/hour")
async def generate_image(request: Request, prompt: str) -> str:
    try:
        # Remove await from the next line
        image = await generate_image_service(prompt)
        # Add a check if image generation failed in the service
        if image == "No image data found in the response.":
            raise HTTPException(status_code=500, detail="Image generation failed.")
        return image
    except Exception as e:
        # Log the actual error for debugging
        logging.error(f"Error generating image for prompt '{prompt}': {e}")
        # Raise a proper HTTP exception instead of returning the error string
        raise HTTPException(
            status_code=500, detail="An error occurred during image generation."
        )


@router.post(
    "/save",
    response_model=ImageResponse,
    summary="Save Generated Image (Auth Required)",
)
@limiter.limit("5/minute;20/hour")
async def save_generated_image(
    request: Request,
    save_request: SaveImageRequest,  # Use the request body model
    current_user: CurrentUser,  # Get authenticated user
    db: DbSession,  # Inject DB session
) -> Image:  # Return type hint can be the SQLAlchemy model directly with orm_mode
    """
    Saves a base64 encoded image string to the user's account in cloud storage.
    Requires authentication.
    """
    if not current_user.user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_uuid = current_user.get_uuid()
    if not user_uuid:  # Ensure UUID conversion worked
        raise HTTPException(status_code=401, detail="Invalid user identifier in token")

    try:
        logging.info(f"User {user_uuid} attempting to save image.")
        # Call the service function to save the image
        db_image = await save_user_image(
            db=db,
            user_id=user_uuid,
            image_base64=save_request.image_base64,
            prompt=save_request.prompt,
        )
        logging.info(f"Successfully saved image {db_image.id} for user {user_uuid}")
        # Pydantic will automatically convert db_image to ImageResponse due to orm_mode
        return db_image

    except HTTPException as e:
        # Re-raise known HTTP exceptions (e.g., from save_user_image)
        raise e
    except Exception as e:
        # Log unexpected errors during saving
        logging.error(f"Error saving image for user {user_uuid}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred while saving the image."
        )
