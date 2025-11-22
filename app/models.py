from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, func, Boolean
from .database import Base
from datetime import datetime, timedelta
import enum
import random

# --- Enum for mail status ---
class MailStatus(enum.Enum):
    pending = "pending"
    completed = "completed"
    overdue = "overdue"

# --- Main Table ---
class Mail(Base):
    __tablename__ = "mails"

    id = Column(Integer, primary_key=True, index=True)
    eksu_ref = Column(String(20), unique=True, index=True)  # ✅ new column
    name = Column(String(200), nullable=True)
    sender = Column(String(200), nullable=True)
    document = Column(Text, nullable=True)
    recipient = Column(String(200), nullable=True)
    date_sent = Column(DateTime, nullable=True)
    status = Column(Enum(MailStatus), nullable=True)
    response_date = Column(DateTime, nullable=True)
    custom_threshold_hours = Column(Integer, nullable=True)  # e.g. 24, 48
    matched_to_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())
    notified = Column(Boolean, default=False)  # To prevent duplicate notifications
    notified_at = Column(DateTime, nullable=True)
    notification_type = Column(String(50), default="system")  # 'system' or 'email'
    reminder_sent_at = Column(DateTime, nullable=True)  # Track when reminder was sent

