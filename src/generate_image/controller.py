from fastapi import APIRouter
from .service import generate_image_service


router = APIRouter(prefix="/image", tags=["Image"])


@router.get("/generate", response_model=str)
def generate_image(prompt: str) -> str:
    try:
        image = generate_image_service(prompt)
        return image
    except Exception as e:
        return str(e)
