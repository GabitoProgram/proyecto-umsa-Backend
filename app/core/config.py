from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Control Acceso Prefacultativo - UMSA"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Base de datos
    DATABASE_URL: str = "postgresql://postgres@localhost:5432/umsa_prefacultativo"

    # JWT y Seguridad
    SECRET_KEY: str = "cambia_esta_clave_por_un_hash_seguro_en_produccion_umsa_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 horas
    APP_CLIENT_KEY: str = "Y6eNTiTvp3swWgQhImbqf97qR1jb287dUVu9IJ6zWrwvwvPY3jcnR8QOgCQm8peJ"

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")


settings = Settings()
