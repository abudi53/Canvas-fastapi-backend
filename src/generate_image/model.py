from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class ImageResponse(BaseModel):
    id: UUID = Field(..., description="The unique identifier of the image.")
    user_id: UUID = Field(
        ..., description="The unique identifier of the user who uploaded the image."
    )
    prompt: str = Field(..., description="The prompt used to generate the image.")
    image_base64: str = Field(
        ..., description="The base64 encoded string of the generated image."
    )

    model_config = ConfigDict(from_attributes=True)


class ImageRequest(BaseModel):
    prompt: str = Field(..., description="The prompt used to generate the image.")


# Add image update on the future
class ImageUpdate(BaseModel):
    prompt: str = Field(..., description="The new prompt for the image.")
    image_base64: str = Field(
        ..., description="The new base64 encoded string of the generated image."
    )
