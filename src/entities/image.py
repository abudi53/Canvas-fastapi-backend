from sqlalchemy import Column, ForeignKey, String, DateTime
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..database.core import Base


class Image(Base):
    id = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    prompt = Column(String, nullable=False)
    image_base64 = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
