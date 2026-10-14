-- Ejecutar sobre la base existente antes de desplegar la nueva aplicación.
-- No elimina usuarios, postulantes, inscripciones ni registros de ingreso.

DROP TABLE IF EXISTS estaciones CASCADE;

ALTER TABLE rostros
    ADD COLUMN IF NOT EXISTS habilitada BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE rostros
    ADD COLUMN IF NOT EXISTS habilitada_por INTEGER REFERENCES usuarios(id_usuario) ON DELETE SET NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'rostros' AND column_name = 'activo'
    ) THEN
        EXECUTE 'UPDATE rostros SET habilitada = activo';
        EXECUTE 'ALTER TABLE rostros DROP COLUMN activo';
    END IF;
END $$;

ALTER TABLE rostros ALTER COLUMN habilitada SET DEFAULT FALSE;
ALTER TABLE huellas ALTER COLUMN habilitada SET DEFAULT FALSE;

ALTER TABLE auditoria ALTER COLUMN id_usuario SET NOT NULL;

UPDATE rostros SET habilitada = FALSE WHERE habilitada IS NULL;
UPDATE huellas SET habilitada = FALSE WHERE habilitada IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_postulante_dedo
    ON huellas (id_postulante, tipo_dedo);