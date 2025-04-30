from fastapi import APIRouter, HTTPException
from .service import generate_image_service
import logging


router = APIRouter(prefix="/image", tags=["Image"])


@router.get("/generate", response_model=str)
async def generate_image(prompt: str) -> str:
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
