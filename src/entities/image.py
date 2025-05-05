from sqlalchemy import Column, ForeignKey, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from ..database.core import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    # Store a reference to the file, not the binary data itself
    file_path = Column(String, nullable=False, unique=True)
    prompt = Column(String, nullable=True)  # Optional: store the prompt used
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Foreign Key to link to the User table
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationship to access the User object from an Image instance
    owner = relationship("User", back_populates="images")

    def __repr__(self):
        return (
            f"<Image(id={self.id}, user_id={self.user_id}, file_path={self.file_path})>"
        )
