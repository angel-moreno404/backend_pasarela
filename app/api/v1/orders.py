from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.models.models import Order, PaymentNotification, User
from app.schemas.schemas import OrderCreate, OrderResponse
from app.services.matching import auto_match_payment
from app.api.v1.auth import get_current_user
from app.api.v1.ws import manager

router = APIRouter(prefix="/orders", tags=["Órdenes E-Commerce"])

@router.post("/", response_model=OrderResponse)
async def create_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Crea una nueva orden pendiente de pago desde la tienda e-commerce.
    Al crearse, revisa si la notificación de pago ya había llegado previamente a la BD.
    """
    query_existing = select(Order).where(Order.order_code == order_in.order_code)
    res_existing = await db.execute(query_existing)
    if res_existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe una orden con ese código")

    new_order = Order(
        order_code=order_in.order_code,
        expected_reference=order_in.expected_reference.strip(),
        expected_amount=order_in.expected_amount,
        expected_bank=order_in.expected_bank,
        customer_name=order_in.customer_name,
        customer_phone=order_in.customer_phone,
        status="PENDING_PAYMENT"
    )
    db.add(new_order)
    await db.flush()

    # Buscar si ya existe un pago capturado sin coincidir que encaje con esta orden recién creada
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
            break

    await db.commit()
    await db.refresh(new_order)
    return new_order

@router.get("/", response_model=List[OrderResponse])
async def list_orders(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista las órdenes creadas en el sistema para el panel de gestión.
    """
    query = select(Order).order_by(Order.created_at.desc())
    if status_filter:
        query = query.where(Order.status == status_filter)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()

@router.get("/code/{order_code}", response_model=OrderResponse)
async def get_order_status(
    order_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Consulta pública del estado de una orden (utilizado por el e-commerce para saber si el pago fue verificado).
    """
    query = select(Order).where(Order.order_code == order_code)
    res = await db.execute(query)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return order
