from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.models import User
from app.api.v1 import auth, payments, orders, ws, stats, client, merchants

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Configuration for CORS (Allowing Vue 3 frontend and Expo mobile app requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Inicializar tablas en la base de datos automáticamente al arrancar
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Intentar añadir columnas si la base de datos SQLite ya existía con esquema previo
        from sqlalchemy import text
        for statement in [
            "ALTER TABLE orders ADD COLUMN merchant_id INTEGER REFERENCES merchant_api_keys(id);",
            "ALTER TABLE orders ADD COLUMN webhook_url VARCHAR;",
            "ALTER TABLE orders ADD COLUMN webhook_status VARCHAR DEFAULT 'NONE';"
        ]:
            try:
                await conn.execute(text(statement))
            except Exception:
                pass # La columna ya existe

    # Crear usuario administrador por defecto si la BD está vacía
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        if not res.scalars().first():
            default_admin = User(
                email="admin@pasarela.com",
                hashed_password=get_password_hash("admin123"),
                full_name="Administrador de Pasarela",
                is_active=True
            )
            db.add(default_admin)
            await db.commit()
            print("🌱 Usuario semilla creado: admin@pasarela.com / admin123")

# Incluir Enrutadores de API v1
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(payments.router, prefix=settings.API_V1_STR)
app.include_router(orders.router, prefix=settings.API_V1_STR)
app.include_router(client.router, prefix=settings.API_V1_STR)
app.include_router(merchants.router, prefix=settings.API_V1_STR)
app.include_router(stats.router, prefix=settings.API_V1_STR)
app.include_router(ws.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs"
    }

