from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.core.config import settings
from app.models.models import PaymentNotification, Order, User
from app.schemas.schemas import (
    PaymentNotificationListenerInput,
    PaymentNotificationResponse,
    OrderMatchRequest
)
from app.services.matching import generate_notification_hash, auto_match_payment
from app.api.v1.auth import get_current_user
from app.api.v1.ws import manager

router = APIRouter(prefix="/payments", tags=["Pagos & Notificaciones"])

@router.post("/listener", response_model=PaymentNotificationResponse)
async def receive_payment_notification(
    payload: PaymentNotificationListenerInput,
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint invocado por la App Móvil Listener para registrar un pago interceptado.
    Valida la clave API de la app móvil, verifica duplicados con Hash único y realiza el matcheo automático.
    """
    if x_api_key != settings.API_KEY_MOBILE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clave API móvil inválida o no proporcionada"
        )

    # 1. Generar Hash anti-duplicado
    notif_hash = generate_notification_hash(
        bank_name=payload.bank_name,
        reference_number=payload.reference_number,
        amount=payload.amount,
        raw_text=payload.raw_text
    )

    # 2. Verificar si el Hash ya existe en BD
    query_existing = select(PaymentNotification).where(PaymentNotification.notification_hash == notif_hash)
    result_existing = await db.execute(query_existing)
    existing_payment = result_existing.scalar_one_or_none()

    if existing_payment:
        # Ya existe en base de datos -> Retornar como duplicado sin crear nuevo registro
        return existing_payment

    # 3. Crear nuevo registro de notificación
    new_payment = PaymentNotification(
        raw_notification_text=payload.raw_text,
        bank_name=payload.bank_name,
        reference_number=payload.reference_number,
        amount=payload.amount,
        notification_hash=notif_hash,
        status="UNMATCHED"
    )
    db.add(new_payment)
    await db.flush()

    # 4. Intentar emparejamiento automático con orden pendiente
    is_matched = await auto_match_payment(db, new_payment)
    await db.commit()
    await db.refresh(new_payment)

    # 5. Broadcast en tiempo real vía WebSockets al panel web
    await manager.broadcast({
        "event": "NEW_PAYMENT",
        "data": {
            "id": new_payment.id,
            "bank_name": new_payment.bank_name,
            "reference_number": new_payment.reference_number,
            "amount": new_payment.amount,
            "status": new_payment.status,
            "matched_order_id": new_payment.matched_order_id,
            "captured_at": new_payment.captured_at.isoformat()
        }
    })

    return new_payment

@router.get("/", response_model=List[PaymentNotificationResponse])
async def list_payments(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista los pagos e intercepciones capturados para mostrar en el panel web.
    """
    query = select(PaymentNotification).order_by(PaymentNotification.captured_at.desc())
    if status_filter:
        query = query.where(PaymentNotification.status == status_filter)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()

@router.post("/manual-match", response_model=PaymentNotificationResponse)
async def manual_match_payment(
    match_data: OrderMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Permite conciliación manual entre un pago capturado y una orden pendiente desde el dashboard web.
    """
    query_pay = select(PaymentNotification).where(PaymentNotification.id == match_data.payment_id)
    res_pay = await db.execute(query_pay)
    payment = res_pay.scalar_one_or_none()

    query_ord = select(Order).where(Order.id == match_data.order_id)
    res_ord = await db.execute(query_ord)
    order = res_ord.scalar_one_or_none()

    if not payment or not order:
        raise HTTPException(status_code=404, detail="Pago u Orden no encontrada")

    if order.status == "PAID":
        raise HTTPException(status_code=400, detail="Esta orden ya ha sido marcada como pagada")

    order.status = "PAID"
    order.matched_payment_id = payment.id
    payment.status = "MATCHED"
    payment.matched_order_id = order.id

    await db.commit()
    await db.refresh(payment)

    await manager.broadcast({
        "event": "PAYMENT_MATCHED",
        "data": {
            "order_id": order.id,
            "order_code": order.order_code,
            "payment_id": payment.id,
            "amount": payment.amount
        }
    })

    return payment
