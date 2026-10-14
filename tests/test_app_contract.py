import pytest
from fastapi import HTTPException

from app.api.deps import require_app_key
from app.core.config import settings
from app.main import app


def test_app_key_accepts_configured_key():
    assert require_app_key(settings.APP_CLIENT_KEY) is None


def test_app_key_rejects_invalid_key():
    with pytest.raises(HTTPException) as error:
        require_app_key("clave-invalida")
    assert error.value.status_code == 401


def test_station_routes_are_removed():
    paths = {route.path for route in app.routes}
    assert not any(path.startswith("/api/v1/estaciones") for path in paths)


def test_required_client_routes_exist():
    paths = {route.path for route in app.routes}
    assert "/api/v1/examenes/activos-ahora" in paths
    assert "/api/v1/examenes/activos-ahora/postulantes" in paths
    assert "/api/v1/marcaciones/verificar-huella" in paths
    assert "/api/v1/marcaciones/verificar-rostro" in paths
    assert "/api/v1/marcacion/verificar-huella" in paths
    assert "/api/v1/marcacion/verificar-rostro" in paths
    assert "/api/v1/reportes/examen/{id_examen}/pdf" in paths
