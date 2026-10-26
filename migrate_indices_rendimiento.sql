-- Índices para acelerar las consultas de marcación (huella y rostro).
-- Se puede ejecutar varias veces sin problema (IF NOT EXISTS).
--
-- Windows (PowerShell), desde la carpeta del backend:
--   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d umsa_prefacultativo -f migrate_indices_rendimiento.sql

-- Rostros: la caché facial consulta solo los habilitados
CREATE INDEX IF NOT EXISTS ix_rostros_habilitada ON rostros (habilitada, id_postulante);
CREATE INDEX IF NOT EXISTS ix_rostros_postulante ON rostros (id_postulante);

-- Inscripciones: se filtran por gestión + carrera + estado en cada marcación y contador
CREATE INDEX IF NOT EXISTS ix_inscripciones_gestion_carrera_estado
    ON inscripciones (id_gestion, id_carrera, estado);
CREATE INDEX IF NOT EXISTS ix_inscripciones_postulante
    ON inscripciones (id_postulante);

-- Asignaciones (aula y asiento)
CREATE INDEX IF NOT EXISTS ix_asignaciones_inscripcion_examen
    ON asignaciones (id_inscripcion, id_examen);
CREATE INDEX IF NOT EXISTS ix_asignaciones_examen
    ON asignaciones (id_examen);

-- Registros de ingreso: "¿ya ingresó?", contadores y últimos ingresos
CREATE INDEX IF NOT EXISTS ix_registros_examen_inscripcion_resultado
    ON registros_ingreso (id_examen, id_inscripcion, resultado);
CREATE INDEX IF NOT EXISTS ix_registros_examen_fecha
    ON registros_ingreso (id_examen, fecha_hora DESC);

-- Exámenes de hoy y asientos habilitados por aula
CREATE INDEX IF NOT EXISTS ix_examenes_fecha ON examenes (fecha);
CREATE INDEX IF NOT EXISTS ix_asientos_aula_habilitado ON asientos (id_aula, habilitado);

-- Actualiza las estadísticas para que PostgreSQL use los índices nuevos
ANALYZE rostros;
ANALYZE inscripciones;
ANALYZE asignaciones;
ANALYZE registros_ingreso;
ANALYZE examenes;
ANALYZE asientos;