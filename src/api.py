from fastapi import FastAPI
from src.auth.controller import router as auth_router
from src.users.controller import router as users_router
from src.image_art.controller import router as generate_image_router


def register_routes(app: FastAPI) -> None:
    """Register all routes for the FastAPI application."""
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(generate_image_router)
