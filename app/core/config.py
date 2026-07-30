import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Pasarela de Pago C2P API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey_pasarela_c2p_2026")
    API_KEY_MOBILE: str = os.getenv("API_KEY_MOBILE", "mobile_listener_secret_key_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 7 days
    
    # Fallback to local SQLite if DATABASE_URL is not set or points to localhost postgres without connection
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite+aiosqlite:///./pasarela.db"
    )

    class Config:
        case_sensitive = True

settings = Settings()
