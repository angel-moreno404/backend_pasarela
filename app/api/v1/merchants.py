import secrets
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.models.models import MerchantApiKey, User
from app.schemas.schemas import MerchantCreate, MerchantResponse
from app.api.v1.auth import get_current_user

router = APIRouter(prefix="/merchants", tags=["Administración de Clientes & API Keys"])

def generate_secure_api_key() -> str:
    """Genera una llave de API segura con prefijo sk_live_bdv_"""
    random_hex = secrets.token_hex(16)
    return f"sk_live_bdv_{random_hex}"

@router.post("/api-keys", response_model=MerchantResponse)
async def create_merchant_api_key(
    merchant_in: MerchantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Crea una nueva llave de API para un sistema cliente / comercio externo.
    """
    new_api_key = generate_secure_api_key()

    merchant = MerchantApiKey(
        merchant_name=merchant_in.merchant_name.strip(),
        api_key=new_api_key,
        webhook_url=merchant_in.webhook_url.strip() if merchant_in.webhook_url else None,
        is_active=True
    )
    db.add(merchant)
    await db.commit()
    await db.refresh(merchant)
    return merchant

@router.get("/api-keys", response_model=List[MerchantResponse])
async def list_merchant_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista todas las llaves de API y clientes registrados en la pasarela.
    """
    query = select(MerchantApiKey).order_by(MerchantApiKey.created_at.desc())
    res = await db.execute(query)
    return res.scalars().all()

@router.patch("/api-keys/{merchant_id}/toggle", response_model=MerchantResponse)
async def toggle_merchant_status(
    merchant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Activa o desactiva la llave de API de un cliente.
    """
    query = select(MerchantApiKey).where(MerchantApiKey.id == merchant_id)
    res = await db.execute(query)
    merchant = res.scalar_one_or_none()

    if not merchant:
        raise HTTPException(status_code=404, detail="Cliente/Llave de API no encontrada")

    merchant.is_active = not merchant.is_active
    await db.commit()
    await db.refresh(merchant)
    return merchant

@router.delete("/api-keys/{merchant_id}")
async def delete_merchant_api_key(
    merchant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina una llave de API de cliente.
    """
    query = select(MerchantApiKey).where(MerchantApiKey.id == merchant_id)
    res = await db.execute(query)
    merchant = res.scalar_one_or_none()

    if not merchant:
        raise HTTPException(status_code=404, detail="Cliente/Llave de API no encontrada")

    await db.delete(merchant)
    await db.commit()
    return {"message": "Llave de API eliminada exitosamente"}
