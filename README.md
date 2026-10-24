# Backend UMSA

API del sistema de control de acceso prefacultativo UMSA. Está construido
con FastAPI, SQLAlchemy y PostgreSQL.

## Requisitos

- Windows 10/11 o Linux.
- Python 3.11 recomendado para este proyecto.
- PostgreSQL  PostgreSQL 14 o superior.
- Git.
- Microsoft Visual C++ Build Tools en Windows si se instala `insightface`
  u otras dependencias nativas.

Python 3.13 puede funcionar para parte de la API, pero Python 3.11 es la
opción recomendada por la compatibilidad de `insightface`, `onnxruntime` y
otras dependencias biométricas.

## Crear la base de datos

Con PostgreSQL instalado, crea la base vacía:

```powershell
psql -U postgres
```

En la consola de PostgreSQL:

```sql
CREATE DATABASE umsa_prefacultativo;
\q
```

Si la base ya existe, no es necesario crearla nuevamente.

## Configurar el entorno

Desde la carpeta del backend:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

En Git Bash, la activación equivalente es:

```bash
source venv/Scripts/activate
```

## Configurar `.env`

Copia el archivo de ejemplo:

```powershell
Copy-Item .env.example .env
```

Edita `.env` y configura tus valores locales:

```dotenv
DATABASE_URL=postgresql://postgres:TU_CONTRASEÑA@localhost:5432/umsa_prefacultativo
SECRET_KEY=GENERA_UNA_CLAVE_LARGA_Y_ALEATORIA
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=720
APP_CLIENT_KEY=GENERA_OTRA_CLAVE_COMPARTIDA
```

`SECRET_KEY` y `APP_CLIENT_KEY` deben tener al menos 32 caracteres y no deben
ser valores de ejemplo. No subas `.env` a Git.

La misma `APP_CLIENT_KEY` debe configurarse en el frontend.

## Inicializar y migrar la base de datos

Primero crea las tablas y tipos ENUM de SQLAlchemy:

```powershell
python init_db.py
```

Después aplica las migraciones SQL, en este orden:

```powershell
psql -U postgres -d umsa_prefacultativo -f migrate_postulantes_contacto.sql
psql -U postgres -d umsa_prefacultativo -f migrate_marcacion_sin_asiento.sql
psql -U postgres -d umsa_prefacultativo -f migrate_remove_stations.sql
```

Si `psql` no está en el PATH de Windows, usa su ruta completa, por ejemplo:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d umsa_prefacultativo -f migrate_postulantes_contacto.sql
```

Las migraciones utilizan `IF NOT EXISTS` en los cambios principales, por lo
que pueden ejecutarse nuevamente cuando sea necesario. Revisa siempre el
resultado de `psql` antes de continuar.

## Crear el usuario inicial

Opcionalmente define una contraseña inicial:

```powershell
$env:ADMIN_INITIAL_PASSWORD="CambiaEstaClavePorUnaSegura"
python seed.py
```

Si no defines `ADMIN_INITIAL_PASSWORD`, el script genera una contraseña
aleatoria y la muestra una sola vez en la consola.

El usuario creado es:

```text
Usuario: admin
Rol: SUPER_ADMIN
```

Cambia la contraseña después del primer inicio de sesión.

## Ejecutar la API

Con el entorno virtual activo:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

URLs útiles:

- Salud: `http://127.0.0.1:8000/health`
- Documentación: `http://127.0.0.1:8000/docs`
- API: `http://127.0.0.1:8000/api/v1`

Si el puerto 8000 está ocupado:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

En ese caso también debes cambiar `API_BASE_URL` en el frontend.

## Lector ZKTeco ZK9500

La API no controla directamente el lector; el frontend usa la SDK local de
ZKTeco para capturar y comparar huellas. La máquina que tenga conectado el
lector necesita la SDK correspondiente y su DLL (`zkfp.dll` o equivalente)
en una ruta que el proyecto pueda encontrar.

La captura biométrica también requiere que las huellas estén registradas y
habilitadas para el examen correspondiente.

## Pruebas

Instala las dependencias de desarrollo:

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## Problemas frecuentes

### Error de conexión a PostgreSQL

Comprueba que el servicio de PostgreSQL esté iniciado, que la base exista y
que `DATABASE_URL` tenga usuario, contraseña, host, puerto y base correctos.

### Claves inválidas al iniciar

Genera claves nuevas de al menos 32 caracteres para `SECRET_KEY` y
`APP_CLIENT_KEY`. No uses los valores de `.env.example`.

### El backend inicia, pero no funciona la biometría

La API puede iniciar aunque algunas dependencias nativas de reconocimiento
facial o la SDK del lector no estén disponibles. Revisa la instalación de
`insightface`, `onnxruntime`, Visual C++ Build Tools y la SDK de ZKTeco.

## Seguridad

Nunca publiques:

- `.env`.
- Contraseñas de PostgreSQL.
- `SECRET_KEY`.
- `APP_CLIENT_KEY`.
- Plantillas biométricas.
- Archivos de datos reales.

