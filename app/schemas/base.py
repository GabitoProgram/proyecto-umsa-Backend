from datetime import date, time
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.usuario import RolUsuario
from app.models.academico import PeriodoGestion

# Token
class Token(BaseModel):
    access_token: str
    token_type: str

# Usuario
class UsuarioBase(BaseModel):
    nombre_completo: str
    genero: Optional[str] = None
    usuario: str
    rol: RolUsuario = RolUsuario.ADMIN
    activo: bool = True

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioOut(UsuarioBase):
    id_usuario: int
    model_config = ConfigDict(from_attributes=True)

# Carrera
class CarreraBase(BaseModel):
    nombre: str
    # El código es opcional: las carreras que se dan de alta solas desde la
    # carga masiva no traen uno, y la columna en la base de datos es nullable.
    codigo: Optional[str] = None
    activa: bool = True

class CarreraCreate(CarreraBase):
    pass

class CarreraOut(CarreraBase):
    id_carrera: int
    model_config = ConfigDict(from_attributes=True)

# Gestión
class GestionBase(BaseModel):
    nombre: str
    anio: int
    periodo: PeriodoGestion
    fecha_inicio: date
    fecha_fin: date
    estado: str = "ACTIVO"

class GestionCreate(GestionBase):
    pass

class GestionOut(GestionBase):
    id_gestion: int
    model_config = ConfigDict(from_attributes=True)

# Aula y Asientos
class AsientoBase(BaseModel):
    numero_asiento: int
    fila: Optional[str] = None
    columna: Optional[int] = None
    habilitado: bool = True

class AsientoOut(AsientoBase):
    id_asiento: int
    id_aula: int
    model_config = ConfigDict(from_attributes=True)

class AulaBase(BaseModel):
    nombre: str
    ubicacion: Optional[str] = None
    capacidad: int
    activa: bool = True

class AulaCreate(AulaBase):
    generar_asientos_auto: bool = True

class AulaOut(AulaBase):
    id_aula: int
    model_config = ConfigDict(from_attributes=True)

# Examen
class ExamenBase(BaseModel):
    id_carrera: int
    id_gestion: int
    materia: str
    fecha: date
    hora_inicio: time
    hora_fin: time
    estado: str = "PROGRAMADO"

class ExamenCreate(ExamenBase):
    pass

class ExamenOut(ExamenBase):
    id_examen: int
    model_config = ConfigDict(from_attributes=True)
