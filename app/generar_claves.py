"""Genera claves nuevas y seguras para el servidor.

Uso:
    python app/generar_claves.py

Copia las dos líneas que imprime en el archivo ``.env`` del SERVIDOR.
La ``APP_CLIENT_KEY`` también hay que ponerla en cada estación de registro
(``config/app_config.json`` del cliente de escritorio).
Nunca subas el ``.env`` ni estas claves a git.
"""
import secrets

print("# Pega estas líneas en el .env del servidor:")
print(f"SECRET_KEY={secrets.token_urlsafe(64)}")
print(f"APP_CLIENT_KEY={secrets.token_hex(32)}")