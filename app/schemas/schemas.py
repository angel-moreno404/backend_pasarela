from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

# --- Auth Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenPayload(BaseModel):
    sub: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Payment Notification Schemas ---
class PaymentNotificationListenerInput(BaseModel):
    raw_text: str = Field(..., description="Texto completo de la notificación push o SMS")
    bank_name: str = Field(..., description="Nombre del banco emisor")
    reference_number: str = Field(..., description="Número de referencia capturado")
    amount: float = Field(..., description="Monto recibido en Bs")
    phone_sender: Optional[str] = None

class PaymentNotificationResponse(BaseModel):
    id: int
    raw_notification_text: str
    bank_name: str
    reference_number: str
    amount: float
    notification_hash: str
    status: str
    matched_order_id: Optional[int] = None
    captured_at: datetime

    class Config:
        from_attributes = True

# --- Order Schemas ---
class OrderCreate(BaseModel):
    order_code: str = Field(..., description="Código de orden e-commerce (ej: ORD-1001)")
    expected_reference: str = Field(..., description="Últimos 4 o 6 dígitos de la referencia introducidos por el cliente")
    expected_amount: float = Field(..., description="Monto esperado del producto/servicio")
    expected_bank: Optional[str] = Field(None, description="Banco origen seleccionado por el cliente")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    order_code: str
    expected_reference: str
    expected_amount: float
    expected_bank: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    status: str
    matched_payment_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OrderMatchRequest(BaseModel):
    order_id: int
    payment_id: int

# --- Merchant / API Key Schemas ---
class MerchantCreate(BaseModel):
    merchant_name: str = Field(..., description="Nombre de la empresa o sistema cliente")
    webhook_url: Optional[str] = Field(None, description="URL HTTP POST donde recibir notificaciones de pago")

class MerchantResponse(BaseModel):
    id: int
    merchant_name: str
    api_key: str
    webhook_url: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Client API Gateway Schemas ---
class ClientOrderCreate(BaseModel):
    order_code: str = Field(..., description="Código único de la factura u orden (ej: FACT-2026-001)")
    expected_reference: str = Field(..., description="Referencia de Pago Móvil introducida por el comprador (completa o últimos dígitos)")
    expected_amount: float = Field(..., description="Monto en Bs. esperado para la transacción")
    expected_bank: Optional[str] = Field(None, description="Banco emisor (ej: 0102 para BDV)")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    webhook_url: Optional[str] = Field(None, description="URL Webhook específica para esta orden (opcional)")

class ClientPaymentVerifyRequest(BaseModel):
    reference_number: str = Field(..., description="Número de referencia de Pago Móvil")
    amount: float = Field(..., description="Monto en Bs")

class ClientPaymentVerifyResponse(BaseModel):
    is_verified: bool
    order_code: Optional[str] = None
    status: str
    reference_number: str
    amount: float
    bank_name: Optional[str] = None
    payment_time: Optional[datetime] = None

# --- Stats / Dashboard Schemas ---
class StatsSummaryResponse(BaseModel):
    total_captured_count: int
    matched_count: int
    unmatched_count: int
    pending_orders_count: int
    total_collected_bs: float
    auto_match_rate_percentage: float


