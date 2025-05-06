from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime


class SaveImageRequest(BaseModel):
    """Request body for saving an image."""

    image_base64: str = Field(..., description="Base64 encoded image data string.")
    prompt: str | None = Field(
        None, description="Optional prompt used to generate the image."
    )


class ImageResponse(BaseModel):
    """Response model for saved image details."""

    id: UUID
    file_path: str  # This will be the GCS blob name
    prompt: str | None
    created_at: datetime  # Use datetime for better typing

    model_config = ConfigDict(
        from_attributes=True
    )  # Enable ORM mode for direct mapping from SQLAlchemy model


# Add image update on the future
class ImageUpdate(BaseModel):
    prompt: str = Field(..., description="The new prompt for the image.")
    image_base64: str = Field(
        ..., description="The new base64 encoded string of the generated image."
    )


class UserImageResponse(BaseModel):
    """Response model for listing a user's image with its access URL."""

    id: UUID
    prompt: str | None
    created_at: datetime
    image_url: str  # The signed URL for accessing the image
