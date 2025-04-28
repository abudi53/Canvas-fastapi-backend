from .api import register_routes
from fastapi import FastAPI
from .logging import configure_logging, LogLevels
from .database.core import engine, Base

configure_logging(LogLevels.INFO)


app = FastAPI()

""" Only uncomment this line if you want to create 
the database tables 
"""

Base.metadata.create_all(bind=engine)

# Register routes
register_routes(app)
