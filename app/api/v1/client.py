from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.models.models import Order, PaymentNotification, MerchantApiKey
from app.schemas.schemas import (
    ClientOrderCreate,
    OrderResponse,
    ClientPaymentVerifyRequest,
    ClientPaymentVerifyResponse
)
from app.services.webhook_service import send_order_webhook
from app.api.v1.ws import manager

router = APIRouter(prefix="/client", tags=["API Pasarela para Clientes & Sistemas Externos"])

async def get_current_merchant(
    x_merchant_key: Optional[str] = Header(None, alias="X-Merchant-Key"),
    db: AsyncSession = Depends(get_db)
) -> MerchantApiKey:
    """
    Validador de seguridad: verifica la clave API enviada en la cabecera X-Merchant-Key.
    """
    if not x_merchant_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta la cabecera X-Merchant-Key con la llave de acceso del cliente."
        )

    query = select(MerchantApiKey).where(
        MerchantApiKey.api_key == x_merchant_key,
        MerchantApiKey.is_active == True
    )
    res = await db.execute(query)
    merchant = res.scalar_one_or_none()

    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Llave de API (X-Merchant-Key) inválida o inactiva."
        )

    return merchant

@router.post("/orders", response_model=OrderResponse)
async def create_client_order(
    order_in: ClientOrderCreate,
    merchant: MerchantApiKey = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db)
):
    """
    Registra una nueva factura/orden desde un sistema externo (e-commerce, POS, facturación).
    Al crearse, revisa automáticamente si la notificación de pago ya habia llegado previamente.
    """
    # Verificar si el order_code ya existe
    query_existing = select(Order).where(Order.order_code == order_in.order_code)
    res_existing = await db.execute(query_existing)
    if res_existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe una orden registrada con el código '{order_in.order_code}'."
        )

    new_order = Order(
        order_code=order_in.order_code,
        expected_reference=order_in.expected_reference.strip(),
        expected_amount=order_in.expected_amount,
        expected_bank=order_in.expected_bank,
        customer_name=order_in.customer_name,
        customer_phone=order_in.customer_phone,
        status="PENDING_PAYMENT",
        merchant_id=merchant.id,
        webhook_url=order_in.webhook_url or merchant.webhook_url
    )
    db.add(new_order)
    await db.flush()

    # Coincidencia retrospectiva: verificar si ya existe una notificación huérfana (UNMATCHED)
    query_unmatched = select(PaymentNotification).where(PaymentNotification.status == "UNMATCHED")
    res_unmatched = await db.execute(query_unmatched)
    unmatched_payments = res_unmatched.scalars().all()

    for pay in unmatched_payments:
        amount_match = abs(new_order.expected_amount - pay.amount) < 0.01
        ref_order = new_order.expected_reference.strip()
        ref_payment = pay.reference_number.strip()
        ref_match = (ref_order in ref_payment) or (ref_payment in ref_order) or (ref_order[-4:] == ref_payment[-4:])

        if amount_match and ref_match:
            new_order.status = "PAID"
            new_order.matched_payment_id = pay.id
            pay.status = "MATCHED"
            pay.matched_order_id = new_order.id

            await manager.broadcast({
                "event": "PAYMENT_MATCHED",
                "data": {
                    "order_id": new_order.id,
                    "order_code": new_order.order_code,
                    "payment_id": pay.id,
                    "amount": pay.amount
                }
            })
            await db.flush()
            # Disparar webhook
            await send_order_webhook(db, new_order, pay)
            break

    await db.commit()
    await db.refresh(new_order)
    return new_order

@router.get("/orders/{order_code}", response_model=OrderResponse)
async def get_client_order(
    order_code: str,
    merchant: MerchantApiKey = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db)
):
    """
    Consulta el estado de una factura/orden registrada por el cliente.
    """
    query = select(Order).where(
        Order.order_code == order_code,
        Order.merchant_id == merchant.id
    )
    res = await db.execute(query)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la orden con el código '{order_code}'."
        )

    return order

@router.post("/orders/verify", response_model=ClientPaymentVerifyResponse)
async def verify_payment(
    req: ClientPaymentVerifyRequest,
    merchant: MerchantApiKey = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica de forma directa si un pago (referencia + monto) ha sido recibido en la pasarela.
    Retorna el estado de verificación y los detalles del pago si existe.
    """
    ref_search = req.reference_number.strip()
    
    # Buscar pago en la BD
    query = select(PaymentNotification).where(
        PaymentNotification.amount == req.amount
    )
    res = await db.execute(query)
    payments = res.scalars().all()

    matched_pay = None
    for pay in payments:
        p_ref = pay.reference_number.strip()
        if (ref_search in p_ref) or (p_ref in ref_search) or (ref_search[-4:] == p_ref[-4:]):
            matched_pay = pay
            break

    if not matched_pay:
        return ClientPaymentVerifyResponse(
            is_verified=False,
            order_code=None,
            status="NOT_FOUND",
            reference_number=req.reference_number,
            amount=req.amount,
            bank_name=None,
            payment_time=None
        )

    # Si se encontró el pago
    order_code = None
    if matched_pay.matched_order_id:
        query_ord = select(Order).where(Order.id == matched_pay.matched_order_id)
        res_ord = await db.execute(query_ord)
        order_obj = res_ord.scalar_one_or_none()
        if order_obj:
            order_code = order_obj.order_code

    return ClientPaymentVerifyResponse(
        is_verified=True,
        order_code=order_code,
        status=matched_pay.status,
        reference_number=matched_pay.reference_number,
        amount=matched_pay.amount,
        bank_name=matched_pay.bank_name,
        payment_time=matched_pay.captured_at
    )

@router.get("/orders", response_model=List[OrderResponse])
async def list_client_orders(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    merchant: MerchantApiKey = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista las órdenes creadas por la integración del cliente.
    """
    query = select(Order).where(Order.merchant_id == merchant.id).order_by(Order.created_at.desc())
    if status_filter:
        query = query.where(Order.status == status_filter)
    query = query.offset(skip).limit(limit)

    res = await db.execute(query)
    return res.scalars().all()
