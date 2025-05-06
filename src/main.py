from .api import register_routes
from fastapi import FastAPI
from .logging import configure_logging, LogLevels

# from .database.core import engine, Base
import os
from fastapi.middleware.cors import CORSMiddleware

configure_logging(LogLevels.INFO)


app = FastAPI()

""" Only uncomment this line if you want to create 
the database tables 
"""

# Base.metadata.create_all(bind=engine)

# Register routes
register_routes(app)

# --- CORS Configuration ---

# Get allowed origins from environment variables
# Use a comma-separated string in your .env or Vercel env vars
# Example: ALLOWED_ORIGINS="https://your-frontend.vercel.app,https://another-trusted-site.com"
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS", ""
)  # Default to empty string if not set
origins = [
    origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()
]

# Fallback for local development if no env var is set
if (
    not origins and os.getenv("VERCEL_ENV") != "production"
):  # VERCEL_ENV is set by Vercel
    origins = [
        "http://localhost",  # Common local dev origin
        "http://localhost:3000",  # Common React/Vue/etc local dev port
        "http://localhost:8080",  # Another common local dev port
        # Add any other local development origins you use
    ]
    print(
        f"WARNING: ALLOWED_ORIGINS not set. Using default development origins: {origins}"
    )


# Add the CORS middleware
# Make sure this is added BEFORE you define your routes/routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # List of allowed origins
    allow_credentials=True,  # Allow cookies/authorization headers
    allow_methods=["*"],  # Allow all standard methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)
