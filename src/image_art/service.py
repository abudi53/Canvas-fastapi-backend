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
from google.oauth2 import service_account
from ..entities.image import Image
# from ..entities.user import User

# --- GCS Configuration ---
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    # Log warning, but allow initialization to proceed; check will happen in save_user_image
    logging.warning("GCS_BUCKET_NAME environment variable not set.")

# Vercel GCP Integration Variables
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_SERVICE_ACCOUNT_EMAIL = os.getenv("GCP_SERVICE_ACCOUNT_EMAIL")
# Vercel stores the private key directly, potentially needing newline replacement
GCP_PRIVATE_KEY = os.getenv("GCP_PRIVATE_KEY", "").replace("\\n", "\n")

# Standard Google Credentials Variable
GOOGLE_APP_CREDS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

storage_client = None
try:
    # Priority 1: Vercel GCP Integration Variables
    if GCP_PROJECT_ID and GCP_SERVICE_ACCOUNT_EMAIL and GCP_PRIVATE_KEY:
        logging.info("Attempting GCS client initialization using Vercel GCP variables.")
        credentials = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": GCP_PROJECT_ID,
                "private_key_id": "",  # Not strictly needed for client, but part of standard format
                "private_key": GCP_PRIVATE_KEY,
                "client_email": GCP_SERVICE_ACCOUNT_EMAIL,
                "client_id": "",  # Not strictly needed
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{GCP_SERVICE_ACCOUNT_EMAIL.replace('@', '%40')}",
            }
        )
        storage_client = storage.Client(project=GCP_PROJECT_ID, credentials=credentials)
        logging.info("GCS client initialized successfully using Vercel GCP variables.")

    # Priority 2: GOOGLE_APPLICATION_CREDENTIALS (path or JSON content)
    elif GOOGLE_APP_CREDS:
        logging.info(
            "Attempting GCS client initialization using GOOGLE_APPLICATION_CREDENTIALS."
        )
        # storage.Client() handles both file path and JSON content in the env var
        storage_client = storage.Client()
        logging.info(
            "GCS client initialized successfully using GOOGLE_APPLICATION_CREDENTIALS."
        )

    # Priority 3: Application Default Credentials (ADC) - for local gcloud auth
    else:
        logging.info(
            "Attempting GCS client initialization using Application Default Credentials (ADC)."
        )
        # storage.Client() will automatically look for ADC if no other creds are found
        storage_client = storage.Client()
        # Check if ADC actually found credentials (might require project ID explicitly if ADC doesn't provide it)
        if not storage_client.project:
            if GCP_PROJECT_ID:  # Use Vercel's project ID if available with ADC
                storage_client = storage.Client(project=GCP_PROJECT_ID)
                logging.info(
                    f"GCS client initialized using ADC, project set to '{GCP_PROJECT_ID}'."
                )
            else:
                # If no project ID found via ADC or env var, it might fail later
                logging.warning(
                    "GCS client initialized using ADC, but project ID could not be determined automatically."
                )
        else:
            logging.info(
                f"GCS client initialized successfully using ADC for project '{storage_client.project}'."
            )


except Exception as e:
    logging.error(
        f"Failed to initialize Google Cloud Storage client: {e}", exc_info=True
    )
    # storage_client remains None

# --- Service Functions ---
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
    # Check if client initialization succeeded AND bucket name is set
    if not storage_client or not GCS_BUCKET_NAME:
        logging.error(
            "Attempted to save image, but GCS is not configured (client init failed or bucket name missing)."
        )
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Image storage is not set up correctly.",
        )

    # Ensure the client has a project ID associated (important for ADC cases)
    if not storage_client.project:
        logging.error(
            "GCS client is missing project ID, cannot proceed with bucket operations."
        )
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Image storage project ID missing.",
        )

    try:
        image_bytes = base64.b64decode(image_base64)

        # Generate a unique blob name (path within the bucket)
        file_extension = ".png"
        blob_name = f"user_images/{user_id}/{uuid.uuid4()}{file_extension}"

        # Get the bucket (uses client's project ID implicitly if not specified)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)

        # Upload the image bytes
        content_type = "image/png"
        blob.upload_from_string(image_bytes, content_type=content_type)

        logging.info(f"Image uploaded to GCS: gs://{GCS_BUCKET_NAME}/{blob_name}")

        # Create database record
        db_image = Image(
            user_id=user_id,
            file_path=blob_name,
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
        logging.error(f"Error interacting with GCS for user {user_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Error interacting with cloud storage."
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Error saving image for user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while saving the image.",
        )
