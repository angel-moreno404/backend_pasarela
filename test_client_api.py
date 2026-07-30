import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_full_client_api_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Login Admin
        login_res = await ac.post("/api/v1/auth/login", data={"username": "admin@pasarela.com", "password": "admin123"})
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Crear Merchant API Key
        merchant_res = await ac.post("/api/v1/merchants/api-keys", json={
            "merchant_name": "Tienda Test E-Commerce",
            "webhook_url": "https://webhook.site/test-pasarela"
        }, headers=auth_headers)
        assert merchant_res.status_code == 200
        merchant_data = merchant_res.json()
        merchant_key = merchant_data["api_key"]
        assert merchant_key.startswith("sk_live_bdv_")

        client_headers = {"X-Merchant-Key": merchant_key}

        # 3. Crear Orden desde Sistema Cliente
        import time
        ref_num = str(time.time_ns())[-8:]
        order_code = f"FACT-TEST-{ref_num}"

        order_res = await ac.post("/api/v1/client/orders", json={
            "order_code": order_code,
            "expected_reference": ref_num,
            "expected_amount": 150.00,
            "customer_name": "Carlos Pérez",
            "customer_phone": "04141234567"
        }, headers=client_headers)
        assert order_res.status_code == 200
        assert order_res.json()["status"] == "PENDING_PAYMENT"

        # 4. Simular Notificación de Pago de App Móvil
        mobile_headers = {"X-API-Key": "mobile_listener_secret_key_2026"}
        pay_res = await ac.post("/api/v1/payments/listener", json={
            "raw_text": f"BDV: Pago Movil por Bs. 150,00 recibido de 04141234567. Ref. {ref_num}",
            "bank_name": "BDV",
            "reference_number": ref_num,
            "amount": 150.00
        }, headers=mobile_headers)
        assert pay_res.status_code == 200
        assert pay_res.json()["status"] == "MATCHED"

        # 5. Consultar Estado de la Orden desde Cliente
        check_order = await ac.get(f"/api/v1/client/orders/{order_code}", headers=client_headers)
        assert check_order.status_code == 200
        assert check_order.json()["status"] == "PAID"

        # 6. Verificar Pago Directo por Referencia + Monto
        verify_res = await ac.post("/api/v1/client/orders/verify", json={
            "reference_number": ref_num,
            "amount": 150.00
        }, headers=client_headers)
        assert verify_res.status_code == 200
        assert verify_res.json()["is_verified"] is True
        assert verify_res.json()["order_code"] == order_code
