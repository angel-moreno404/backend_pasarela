from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.core.database import get_db
from app.models.models import PaymentNotification, Order, User
from app.schemas.schemas import StatsSummaryResponse
from app.api.v1.auth import get_current_user

router = APIRouter(prefix="/stats", tags=["Estadísticas & Métricas"])

@router.get("/summary", response_model=StatsSummaryResponse)
async def get_stats_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna resumen en tiempo real de métricas KPI para el Dashboard Web.
    """
    # 1. Total pagos capturados
    res_captured = await db.execute(select(func.count(PaymentNotification.id)))
    total_captured_count = res_captured.scalar() or 0

    # 2. Pagos conciliados (MATCHED)
    res_matched = await db.execute(
        select(func.count(PaymentNotification.id)).where(PaymentNotification.status == "MATCHED")
    )
    matched_count = res_matched.scalar() or 0

    # 3. Pagos sin conciliar (UNMATCHED)
    res_unmatched = await db.execute(
        select(func.count(PaymentNotification.id)).where(PaymentNotification.status == "UNMATCHED")
    )
    unmatched_count = res_unmatched.scalar() or 0

    # 4. Órdenes pendientes (PENDING_PAYMENT)
    res_pending_orders = await db.execute(
        select(func.count(Order.id)).where(Order.status == "PENDING_PAYMENT")
    )
    pending_orders_count = res_pending_orders.scalar() or 0

    # 5. Total de Bolívares recaudados de pagos conciliados
    res_total_bs = await db.execute(
        select(func.sum(PaymentNotification.amount)).where(PaymentNotification.status == "MATCHED")
    )
    total_collected_bs = float(res_total_bs.scalar() or 0.0)

    # 6. Tasa de automatización de conciliación
    auto_match_rate_percentage = 0.0
    if total_captured_count > 0:
        auto_match_rate_percentage = round((matched_count / total_captured_count) * 100, 2)

    return {
        "total_captured_count": total_captured_count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "pending_orders_count": pending_orders_count,
        "total_collected_bs": total_collected_bs,
        "auto_match_rate_percentage": auto_match_rate_percentage
    }
