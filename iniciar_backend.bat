@echo off
REM Arranca el backend UMSA con los ajustes de rendimiento.
REM Guardalo en la carpeta del backend (junto a la carpeta "venv" y "app").
cd /d %~dp0
call venv\Scripts\activate.bat

REM Tamano de deteccion facial (480 = rapido; 640 = mas preciso con rostros lejanos)
set FACE_DET_SIZE=480
REM Fotos analizadas a la vez (2 va bien en la mayoria de PCs; sube a 3-4 si tienes 8+ nucleos)
set FACE_MAX_CONCURRENT=2

REM 1 solo proceso: comparte el modelo y la cache de rostros en memoria.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
pause