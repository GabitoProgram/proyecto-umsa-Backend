import hashlib
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Huellas SHA-256 de claves que estuvieron publicadas en el repositorio.
# Se guardan solo sus huellas: sirven para negarse a arrancar con ellas sin
# volver a publicarlas. Cualquier clave nueva generada con
# ``python app/generar_claves.py`` es aceptada.
_CLAVES_PUBLICADAS = {
    "b2275570900cd07d5c297a4129dcea714fb0de35713637842a6a97f5ed7c4a70",
    "fb83debb5a75ab5a07ff3b60b273f119785346d73539e02cab7131bd9e10be59",
}
_LARGO_MINIMO_CLAVE = 32


class Settings(BaseSettings):
    PROJECT_NAME: str = "Control Acceso Prefacultativo - UMSA"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Base de datos
    DATABASE_URL: str = "postgresql://postgres@localhost:5432/umsa_prefacultativo"

    # JWT y Seguridad
    # Sin valor por defecto: tienen que venir del archivo .env del servidor.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12 horas
    APP_CLIENT_KEY: str

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    @field_validator("SECRET_KEY", "APP_CLIENT_KEY")
    @classmethod
    def _validar_clave(cls, valor: str, info) -> str:
        nombre = info.field_name
        ayuda = "Genera una nueva con:  python app/generar_claves.py"
        if valor.upper().startswith(("CAMBIA", "GENERA")):
            raise ValueError(f"{nombre} sigue con el valor de ejemplo. {ayuda}")
        if len(valor) < _LARGO_MINIMO_CLAVE:
            raise ValueError(
                f"{nombre} debe tener al menos {_LARGO_MINIMO_CLAVE} caracteres. {ayuda}"
            )
        if hashlib.sha256(valor.encode("utf-8")).hexdigest() in _CLAVES_PUBLICADAS:
            raise ValueError(
                f"{nombre} es una clave que estuvo publicada en el repositorio y "
                f"ya no es segura. {ayuda}"
            )
        return valor


settings = Settings()