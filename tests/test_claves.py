import hashlib
import secrets

import pytest
from pydantic import ValidationError

from app.core import config


def _crear(**claves):
    base = {"SECRET_KEY": secrets.token_urlsafe(48), "APP_CLIENT_KEY": secrets.token_hex(32)}
    base.update(claves)
    return config.Settings(_env_file=None, **base)


def test_acepta_claves_generadas():
    assert _crear().SECRET_KEY


def test_rechaza_clave_corta():
    with pytest.raises(ValidationError):
        _crear(SECRET_KEY="corta")


def test_rechaza_valor_de_ejemplo():
    with pytest.raises(ValidationError):
        _crear(APP_CLIENT_KEY="GENERA_UNA_CLAVE_ALEATORIA_LARGA_AQUI_0000")


def test_rechaza_clave_publicada(monkeypatch):
    publicada = "esta-clave-estuvo-publicada-" + "x" * 20
    huella = hashlib.sha256(publicada.encode()).hexdigest()
    monkeypatch.setattr(config, "_CLAVES_PUBLICADAS", {huella})
    with pytest.raises(ValidationError):
        _crear(SECRET_KEY=publicada)