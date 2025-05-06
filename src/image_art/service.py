# from huggingface_hub import InferenceClient
from google import genai
from google.genai import types
from typing import List, Dict, Any
from datetime import timedelta
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
import asyncio
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
    prompt_template: str = "Generate an image of a {prompt} with a width of 640 and a height of 352 EXPLICITLY."

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            contents=prompt_template.format(prompt=prompt),
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
    except Exception as e:
        logging.error(f"Error during generate_content call: {e}", exc_info=True)
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

    # Define sync helper for DB commit/refresh to run in thread
    def _commit_and_refresh_db(session: Session, image_obj: Image):
        try:
            session.add(image_obj)
            session.commit()
            session.refresh(image_obj)
            logging.info(
                f"Image record committed and refreshed in DB for user {image_obj.user_id} with path {image_obj.file_path}"
            )
        except Exception as commit_exc:
            logging.error(
                f"Database commit/refresh failed: {commit_exc}", exc_info=True
            )
            session.rollback()  # Rollback on commit/refresh error
            # Re-raise to be caught by the outer try...except
            raise commit_exc

    try:
        # CPU-bound, no await needed
        image_bytes = base64.b64decode(image_base64)

        # Generate a unique blob name (path within the bucket)
        file_extension = ".png"
        blob_name = f"user_images/{user_id}/{uuid.uuid4()}{file_extension}"

        # Get the bucket (sync)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        # Create a blob object (sync)
        blob = bucket.blob(blob_name)

        # Upload the image bytes in a separate thread
        content_type = "image/png"
        logging.info(f"Uploading image to GCS: gs://{GCS_BUCKET_NAME}/{blob_name}")
        # Use await asyncio.to_thread for the blocking upload
        await asyncio.to_thread(
            blob.upload_from_string, image_bytes, content_type=content_type
        )
        logging.info("Successfully uploaded image to GCS.")

        # Create database record object (sync)
        db_image = Image(
            user_id=user_id,
            file_path=blob_name,
            prompt=prompt,
        )

        # Add, commit, and refresh in a separate thread
        await asyncio.to_thread(_commit_and_refresh_db, db, db_image)

        return db_image

    except binascii.Error as e:
        logging.error(f"Error decoding base64 image for user {user_id}: {e}")
        raise HTTPException(status_code=400, detail="Invalid image data format.")
    except google_exceptions.GoogleAPIError as e:
        # This might be caught inside to_thread or directly if client interaction fails before upload
        logging.error(f"Error interacting with GCS for user {user_id}: {e}")
        # Rollback might be needed if error happens after add but before/during commit
        # The helper function _commit_and_refresh_db handles rollback on commit error
        # If GCS error happens before DB commit, rollback isn't strictly needed but doesn't hurt
        try:
            db.rollback()
        except Exception as rb_exc:
            logging.error(f"Rollback failed after GCS error: {rb_exc}")
        raise HTTPException(
            status_code=500, detail="Error interacting with cloud storage."
        )
    except Exception as e:
        # Catch potential errors from _commit_and_refresh_db or other unexpected issues
        logging.error(f"Error saving image for user {user_id}: {e}", exc_info=True)
        # Ensure rollback happens for any exception during the process
        try:
            db.rollback()
        except Exception as rb_exc:
            logging.error(f"Rollback failed after general error: {rb_exc}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while saving the image.",
        )


async def get_user_images_with_urls(db: Session, user_id: UUID) -> List[Dict[str, Any]]:
    """Fetches user images from DB and generates signed GCS URLs."""
    if not storage_client or not GCS_BUCKET_NAME:
        logging.error(
            "Attempted to list images, but GCS is not configured (client init failed or bucket name missing)."
        )
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Image storage is not set up correctly.",
        )
    if not storage_client.project:
        logging.error("GCS client is missing project ID, cannot list images.")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Image storage project ID missing.",
        )

    # Define sync helper for DB query
    def _fetch_images_db(session: Session, user_uuid: UUID) -> List[Image]:
        try:
            images = (
                session.query(Image)
                .filter(Image.user_id == user_uuid)
                .order_by(Image.created_at.desc())
                .all()
            )
            logging.info(
                f"Fetched {len(images)} image records for user {user_uuid} from DB."
            )
            return images
        except Exception as db_exc:
            logging.error(
                f"Database query failed for user {user_uuid}: {db_exc}", exc_info=True
            )
            raise db_exc  # Re-raise to be caught by outer try...except

    # Define sync helper for generating a signed URL
    def _generate_signed_url_sync(blob_name: str) -> str:
        try:
            bucket = storage_client.bucket(GCS_BUCKET_NAME)  # type: ignore
            blob = bucket.blob(blob_name)
            # Generate a signed URL valid for 15 minutes (adjust as needed)
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=15),
                method="GET",
            )
            return url
        except google_exceptions.NotFound:
            logging.error(f"GCS blob not found: {blob_name}")
            # Decide how to handle: return None, raise specific error, return placeholder URL?
            # Returning None or an empty string might be suitable for the controller to filter.
            return ""
        except Exception as url_exc:
            logging.error(
                f"Failed to generate signed URL for {blob_name}: {url_exc}",
                exc_info=True,
            )
            raise url_exc  # Re-raise

    try:
        # Fetch image records from DB in a thread
        user_images = await asyncio.to_thread(_fetch_images_db, db, user_id)

        image_data_with_urls = []

        # Generate signed URLs concurrently using asyncio.gather
        url_tasks = []
        for image in user_images:
            if image.file_path:  # type: ignore
                url_tasks.append(
                    asyncio.to_thread(_generate_signed_url_sync, image.file_path)  # type: ignore
                )
            else:
                # Handle cases where file_path might be missing (shouldn't happen ideally)
                logging.warning(
                    f"Image record {image.id} for user {user_id} has no file_path."
                )
                # Add a placeholder or skip? Adding None to match task list length if needed.
                # Or structure differently to avoid needing placeholders. Let's restructure slightly.
                pass  # Skip if no file_path

        # Filter images that have a file_path before creating tasks
        images_with_paths = [img for img in user_images if img.file_path]  # type: ignore
        url_tasks = [
            asyncio.to_thread(_generate_signed_url_sync, img.file_path)  # type: ignore
            for img in images_with_paths
        ]

        # Run URL generation tasks concurrently
        signed_urls = await asyncio.gather(*url_tasks, return_exceptions=True)

        # Combine image data with generated URLs
        for image, url_or_exc in zip(images_with_paths, signed_urls):
            if isinstance(url_or_exc, Exception):
                # Log the error captured by gather
                logging.error(
                    f"Failed to get signed URL for image {image.id} (path: {image.file_path}): {url_or_exc}"
                )
                image_url = None  # Indicate failure
            elif (
                not url_or_exc
            ):  # Handle empty string case from _generate_signed_url_sync
                logging.warning(
                    f"Signed URL generation returned empty for image {image.id} (path: {image.file_path}), likely blob not found."
                )
                image_url = None
            else:
                image_url = url_or_exc

            # Append data only if URL generation was successful (or handle failures differently)
            if image_url:
                image_data_with_urls.append(
                    {
                        "id": image.id,
                        "file_path": image.file_path,  # Keep original path for reference if needed
                        "prompt": image.prompt,
                        "created_at": image.created_at,
                        "image_url": image_url,  # The temporary access URL
                    }
                )
            # Else: Decide if you want to include records where URL generation failed

        logging.info(
            f"Prepared {len(image_data_with_urls)} image entries with signed URLs for user {user_id}."
        )
        return image_data_with_urls

    except Exception as e:
        # Catch errors from DB query or URL generation helpers
        logging.error(
            f"Error retrieving images or URLs for user {user_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while retrieving user images.",
        )
