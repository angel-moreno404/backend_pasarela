import httpx
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Order, PaymentNotification

logger = logging.getLogger("webhook_service")

async def send_order_webhook(db: AsyncSession, order: Order, payment: PaymentNotification = None):
    """
    Envía una notificación Webhook HTTP POST al sistema cliente cuando la orden se marca como PAID.
    """
    target_url = order.webhook_url
    if not target_url and order.merchant:
        target_url = order.merchant.webhook_url

    if not target_url:
        logger.info(f"Order #{order.order_code} no tiene webhook_url configurado. Omitiendo envío.")
        return False

    payload = {
        "event": "ORDER_PAYMENT_VERIFIED",
        "data": {
            "order_code": order.order_code,
            "status": order.status,
            "expected_amount": order.expected_amount,
            "expected_reference": order.expected_reference,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "payment": {
                "id": payment.id if payment else None,
                "bank_name": payment.bank_name if payment else None,
                "reference_number": payment.reference_number if payment else None,
                "amount": payment.amount if payment else None,
                "captured_at": payment.captured_at.isoformat() if payment and payment.captured_at else None,
            } if payment else None
        }
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(target_url, json=payload, headers={
                "User-Agent": "PasarelaBDV-Webhook/1.0",
                "Content-Type": "application/json"
            })
            if response.status_code in [200, 201, 202, 204]:
                order.webhook_status = "SENT"
                logger.info(f"Webhook enviado exitosamente a {target_url} para orden {order.order_code}")
                await db.flush()
                return True
            else:
                order.webhook_status = "FAILED"
                logger.warning(f"Error respondiendo webhook {target_url}: HTTP {response.status_code}")
                await db.flush()
                return False
    except Exception as e:
        order.webhook_status = "FAILED"
        logger.error(f"Excepción al enviar webhook a {target_url}: {str(e)}")
        await db.flush()
        return False
