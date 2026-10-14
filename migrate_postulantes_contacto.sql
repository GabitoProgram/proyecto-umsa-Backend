-- Contacto del postulante.
--
-- La carga masiva desde Excel trae «correo» y «direccion», pero la tabla
-- postulantes no tenía esas columnas. Son opcionales: el registro manual
-- sigue funcionando sin ellas.
--
-- Aplicar:  psql -h localhost -U postgres -d proyecto -f backend/migrate_postulantes_contacto.sql

ALTER TABLE postulantes ADD COLUMN IF NOT EXISTS correo    VARCHAR;
ALTER TABLE postulantes ADD COLUMN IF NOT EXISTS direccion VARCHAR;

COMMENT ON COLUMN postulantes.correo    IS 'Correo electrónico del postulante (opcional, viene del Excel)';
COMMENT ON COLUMN postulantes.direccion IS 'Dirección domiciliaria del postulante (opcional, viene del Excel)';
