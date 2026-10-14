from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict

class PostulanteBase(BaseModel):
    ci: str
    nombres: str
    apellidos: str
    genero: Optional[str] = None
    telefono: Optional[str] = None
    correo: Optional[str] = None
    direccion: Optional[str] = None
    fecha_nacimiento: Optional[date] = None

class PostulanteCreate(PostulanteBase):
    pass


class PostulanteUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    genero: Optional[str] = None
    telefono: Optional[str] = None
    correo: Optional[str] = None
    direccion: Optional[str] = None
    fecha_nacimiento: Optional[date] = None

class PostulanteResponse(BaseModel):
    id_postulante: int
    ci: str
    nombres: str
    apellidos: str
    genero: Optional[str] = None
    telefono: Optional[str] = None
    correo: Optional[str] = None
    direccion: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    estado_biometria: Optional[str] = "PENDIENTE"
    origen_registro: Optional[str] = "MANUAL"
    fecha_registro: Optional[datetime] = None
    # tiene_rostro: existe y está habilitado (aprobado por un administrador)
    tiene_rostro: bool = False
    # rostro_registrado: existe un registro facial aunque aún no esté habilitado
    rostro_registrado: bool = False
    id_rostro: Optional[int] = None
    cantidad_huellas: int = 0

    model_config = ConfigDict(from_attributes=True)

PostulanteOut = PostulanteResponse
