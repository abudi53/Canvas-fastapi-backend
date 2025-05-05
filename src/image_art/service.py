# from huggingface_hub import InferenceClient
from google import genai
from google.genai import types
import base64
import binascii
import os
import uuid
from sqlalchemy.orm import Session
import logging
from fastapi import HTTPException
from uuid import UUID
from google.cloud import storage
from google.api_core import exceptions as google_exceptions
from ..entities.image import Image
# from ..entities.user import User

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    logging.error("GCS_BUCKET_NAME environment variable not set.")

try:
    storage_client = storage.Client()
except Exception as e:
    logging.error(f"Failed to initialize Google Cloud Storage client: {e}")
    storage_client = None  # Handle cases where client init fails


# Docs: Generate Image on bytes, encode it to base64, and return it as a string
# https://ai.google.dev/gemini-api/docs/image-generation


async def generate_image_service(prompt: str) -> str:
    # Initialize client inside the function
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    prompt_template: str = (
        "Generate an image of a {prompt} with a width of 640 and a height of 352."
    )
    logging.info(f"Generating image for prompt: {prompt}")

    # Add logging before the call
    logging.info("Attempting to call client.aio.models.generate_content")
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            contents=prompt_template.format(prompt=prompt),
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        # Add logging after the call
        logging.info(
            f"Response received successfully: {response.candidates[0].finish_reason if response.candidates else 'No candidates'}"
        )  # Log finish reason or indicate no candidates
    except Exception as e:
        logging.error(
            f"Error during generate_content call: {e}", exc_info=True
        )  # Log full exception
        # Re-raise the exception or handle it appropriately
        raise HTTPException(
            status_code=500, detail=f"Google GenAI API call failed: {e}"
        )

    if not response.candidates:
        logging.warning("No candidates found in the response.")
        return "No image data found in the response."

    for part in response.candidates[0].content.parts:  # type: ignore
        if part.inline_data is not None:
            base64encoded_image = base64.b64encode(part.inline_data.data).decode(  # type: ignore
                "utf-8"
            )
            return base64encoded_image

    logging.warning("No inline_data found in response parts.")
    return "No image data found in the response."


async def save_user_image(
    db: Session, user_id: UUID, image_base64: str, prompt: str | None = None
) -> Image:
    """Decodes base64 image, uploads it to GCS, and creates DB record."""
    if not storage_client or not GCS_BUCKET_NAME:
        raise HTTPException(
            status_code=500, detail="Google Cloud Storage is not configured correctly."
        )

    try:
        image_bytes = base64.b64decode(image_base64)

        # Generate a unique blob name (path within the bucket)
        file_extension = ".png"  # Assuming PNG, adjust if needed
        # Use user ID in the path for organization
        blob_name = f"user_images/{user_id}/{uuid.uuid4()}{file_extension}"

        # Get the bucket
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        # Create a blob object
        blob = bucket.blob(blob_name)

        # Upload the image bytes
        # Determine content type (important for browser rendering if accessed directly)
        content_type = "image/png"  # Adjust if format varies
        blob.upload_from_string(image_bytes, content_type=content_type)

        logging.info(f"Image uploaded to GCS: gs://{GCS_BUCKET_NAME}/{blob_name}")

        # Create database record - store the GCS blob name as the file_path
        db_image = Image(
            user_id=user_id,
            file_path=blob_name,  # Store the GCS object path/name
            prompt=prompt,
        )
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
        logging.info(
            f"Image record created in DB for user {user_id} with path {blob_name}"
        )
        return db_image

    except binascii.Error as e:
        logging.error(f"Error decoding base64 image for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid image data format.")
    except google_exceptions.GoogleAPIError as e:
        logging.error(f"Error uploading image to GCS for user {user_id}: {e}")
        db.rollback()  # Rollback DB if GCS upload failed
        raise HTTPException(
            status_code=500, detail="Error uploading image to cloud storage."
        )
    except Exception as e:
        db.rollback()  # Rollback DB on any other error
        logging.error(f"Error saving image for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while saving the image.",
        )
