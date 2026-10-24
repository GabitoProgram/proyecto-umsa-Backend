"""Claves efímeras para las pruebas: nunca se usan claves reales ni fijas."""
import os
import secrets

os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
os.environ.setdefault("APP_CLIENT_KEY", secrets.token_hex(32))