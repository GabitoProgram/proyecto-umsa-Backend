-- Migración: permitir registrar ingresos sin asignación de asiento.
-- La inscripción vigente basta para habilitar el ingreso a los exámenes
-- de la carrera/gestión. Se guarda el examen e inscripción directamente.
--
-- Ejecutar sobre la base de datos del sistema:
--   psql -U postgres -d proyecto -f migrate_marcacion_sin_asiento.sql

ALTER TABLE registros_ingreso
    ADD COLUMN IF NOT EXISTS id_examen INTEGER REFERENCES examenes(id_examen),
    ADD COLUMN IF NOT EXISTS id_inscripcion INTEGER REFERENCES inscripciones(id_inscripcion);

CREATE INDEX IF NOT EXISTS ix_registros_ingreso_id_examen
    ON registros_ingreso(id_examen);

CREATE INDEX IF NOT EXISTS ix_registros_ingreso_id_inscripcion
    ON registros_ingreso(id_inscripcion);
