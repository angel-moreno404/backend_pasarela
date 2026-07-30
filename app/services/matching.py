import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import Order, PaymentNotification

from app.services.webhook_service import send_order_webhook

def generate_notification_hash(bank_name: str, reference_number: str, amount: float, raw_text: str) -> str:
    """
    Genera un hash SHA256 único a partir de los datos clave de la notificación
    para evitar registrar transacciones duplicadas.
    """
    clean_ref = reference_number.strip()
    clean_bank = bank_name.strip().upper()
    amount_str = f"{amount:.2f}"
    raw_snippet = raw_text.strip()[:30] # tomar fragmento inicial
    
    unique_string = f"{clean_bank}:{clean_ref}:{amount_str}:{raw_snippet}"
    return hashlib.sha256(unique_string.encode('utf-8')).hexdigest()

async def auto_match_payment(db: AsyncSession, payment: PaymentNotification) -> bool:
    """
    Busca automáticamente una orden en estado PENDING_PAYMENT que coincida con:
    1. El monto exacto (o con margen < 0.01)
    2. La referencia (los últimos dígitos de la referencia enviada por la orden coinciden con la referencia capturada)
    """
    query = select(Order).where(Order.status == "PENDING_PAYMENT")
    result = await db.execute(query)
    pending_orders = result.scalars().all()

    for order in pending_orders:
        # Verificar coincidencia de monto
        amount_match = abs(order.expected_amount - payment.amount) < 0.01

        # Coincidencia de referencia (admite referencias completas o últimos 4-6 dígitos)
        ref_order = order.expected_reference.strip()
        ref_payment = payment.reference_number.strip()
        ref_match = (ref_order in ref_payment) or (ref_payment in ref_order) or (ref_order[-4:] == ref_payment[-4:])

        if amount_match and ref_match:
            # Marcar orden como pagada
            order.status = "PAID"
            order.matched_payment_id = payment.id

            # Marcar notificación como coincidente
            payment.status = "MATCHED"
            payment.matched_order_id = order.id

            await db.flush()
            # Disparar webhook si el cliente tiene URL configurada
            await send_order_webhook(db, order, payment)
            return True

    return False
