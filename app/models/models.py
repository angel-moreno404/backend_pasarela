from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String, unique=True, index=True, nullable=False) # e.g. ORD-1002
    expected_reference = Column(String, index=True, nullable=False)
    expected_amount = Column(Float, nullable=False)
    expected_bank = Column(String, nullable=True) # e.g. 0102 (BDV), 0134 (Banesco)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    status = Column(String, default="PENDING_PAYMENT") # PENDING_PAYMENT, PAID, CANCELLED
    matched_payment_id = Column(Integer, ForeignKey("payment_notifications.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payment = relationship("PaymentNotification", foreign_keys=[matched_payment_id])

class PaymentNotification(Base):
    __tablename__ = "payment_notifications"

    id = Column(Integer, primary_key=True, index=True)
    raw_notification_text = Column(Text, nullable=False)
    bank_name = Column(String, nullable=False) # e.g. BDV, Banesco, Mercantil
    reference_number = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    notification_hash = Column(String, unique=True, index=True, nullable=False) # Hash anti-duplicados
    status = Column(String, default="UNMATCHED") # UNMATCHED, MATCHED, DUPLICATE
    matched_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)

    order = relationship("Order", foreign_keys=[matched_order_id])

