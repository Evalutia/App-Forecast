USE evalutia;

-- Issue #41: catalogo de grupos comerciales del ERP + columna grupo_id en articulos.
--
-- Reemplaza el filtro implicito GROUPS=201 del ETL (hoy solo a nivel de parametro
-- SOAP, nunca persistido) por un catalogo real. visible_planilla controla que
-- grupos aparecen como filtro en la planilla de reposicion; aplica_modelo_econometrico
-- controla que SKUs procesa el worker de prediccion (issue #43).
--
-- A diferencia de familia_id/genero_id/marca_id/seccion_id/temporada_id (enteros
-- sueltos sin FK), grupo_id si lleva FOREIGN KEY real: controla logica de negocio
-- critica (que SKUs entran al modelo econometrico) y un codigo huerfano ahi no
-- puede pasar desapercibido.
--
-- Sin endpoint/CRUD para administrar grupos (decision explicita) -- seed unico
-- desde el PDF de grupos del cliente (sesion 2026-06-23) + UPDATE manual cuando
-- haga falta tocar visible_planilla o aplica_modelo_econometrico.

CREATE TABLE IF NOT EXISTS grupos (
  id                          INT UNSIGNED  NOT NULL,
  descripcion                 VARCHAR(255)  NOT NULL,
  visible_planilla            BOOLEAN       NOT NULL DEFAULT TRUE,
  aplica_modelo_econometrico  BOOLEAN       NOT NULL DEFAULT FALSE,
  ts_carga                    TIMESTAMP(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en              TIMESTAMP(6)          NULL ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Seed desde el PDF de grupos del cliente. visible_planilla = false solo para
-- 199 (sin valor para inventario) y 200 (exportacion web). aplica_modelo_econometrico
-- = true solo para 201.
INSERT INTO grupos (id, descripcion, visible_planilla, aplica_modelo_econometrico) VALUES
  (5,   'TINTA CPT SIN CABEZAL',          TRUE,  FALSE),
  (6,   'CINTA MATRICIAL CPT',            TRUE,  FALSE),
  (10,  'TINTA CPT CON CABEZAL',          TRUE,  FALSE),
  (15,  'TONER COMPATIBLE',               TRUE,  FALSE),
  (20,  'RECARGA DE TINTA',               TRUE,  FALSE),
  (21,  'RECICLADO TINTA',                TRUE,  FALSE),
  (22,  'SISTEMA CONTINUO',               TRUE,  FALSE),
  (23,  'INSUMOS RECARGA TINTA',          TRUE,  FALSE),
  (24,  'Botella tinta (Excepto taller)', TRUE,  FALSE),
  (25,  'RECARGA TONER',                  TRUE,  FALSE),
  (26,  'RECICLADO TONER',                TRUE,  FALSE),
  (27,  'INSUMOS RECARGA TONER',          TRUE,  FALSE),
  (28,  'KIT SISTEMA CONTÍNUO',           TRUE,  FALSE),
  (30,  'TINTA ORIGINAL',                 TRUE,  FALSE),
  (31,  'CINTA MATRICIAL OEM',            TRUE,  FALSE),
  (35,  'TONER ORIGINAL',                 TRUE,  FALSE),
  (40,  'IMPRESORAS',                     TRUE,  FALSE),
  (41,  'IMPRESORAS TERMICAS',            TRUE,  FALSE),
  (42,  'CABLES AUDIO VIDEO',             TRUE,  FALSE),
  (43,  'CONECTIVIDAD',                   TRUE,  FALSE),
  (44,  'CONTROL TV BOX',                 TRUE,  FALSE),
  (50,  'PERIFÉRICOS',                    TRUE,  FALSE),
  (51,  'JOYSTICK ANDROID',               TRUE,  FALSE),
  (52,  'JOYSTICK PS4',                   TRUE,  FALSE),
  (53,  'TV BOX',                         TRUE,  FALSE),
  (54,  'CONSOLAS',                       TRUE,  FALSE),
  (55,  'CAMARAS INALAMBRICAS',           TRUE,  FALSE),
  (56,  'GABINETES',                      TRUE,  FALSE),
  (57,  'FAN COOLER',                     TRUE,  FALSE),
  (58,  'PARLANTES PC',                   TRUE,  FALSE),
  (59,  'PARLANTES BLUETOOTH',            TRUE,  FALSE),
  (60,  'PAPEL',                          TRUE,  FALSE),
  (61,  'SMARTWATCH',                     TRUE,  FALSE),
  (62,  'SILLAS GAMER',                   TRUE,  FALSE),
  (63,  'PEN DRIVE',                      TRUE,  FALSE),
  (64,  'CABLES CELULAR',                 TRUE,  FALSE),
  (65,  'CARGADORES DE CELULARES',        TRUE,  FALSE),
  (66,  'AURICULARES CABLEADOS',          TRUE,  FALSE),
  (67,  'AURICULAR INALÁMBRICO',          TRUE,  FALSE),
  (68,  'SOPORTE CELULAR p- AUTO',        TRUE,  FALSE),
  (69,  'LAPTOP',                         TRUE,  FALSE),
  (70,  'Cajas',                          TRUE,  FALSE),
  (71,  'PERIFERICOS GAMING',             TRUE,  FALSE),
  (72,  'PERIFERICOS OFFICE',             TRUE,  FALSE),
  (73,  'MONITORES',                      TRUE,  FALSE),
  (74,  'PC',                             TRUE,  FALSE),
  (75,  'MEMORIAS',                       TRUE,  FALSE),
  (76,  'FUENTE DE PODER',                TRUE,  FALSE),
  (77,  'DISCOS SDD HDD',                 TRUE,  FALSE),
  (78,  'PROCESADORES',                   TRUE,  FALSE),
  (79,  'MOTHERBOARD',                    TRUE,  FALSE),
  (80,  'MARKETING',                      TRUE,  FALSE),
  (81,  'SOPORTE TV',                     TRUE,  FALSE),
  (82,  'CELULARES',                      TRUE,  FALSE),
  (83,  'MICROFONO',                      TRUE,  FALSE),
  (84,  'FUNDA PARA CELULAR',             TRUE,  FALSE),
  (85,  'TABLET',                         TRUE,  FALSE),
  (86,  'ASPIRADORAS',                    TRUE,  FALSE),
  (87,  'LAPIZ P TABLET',                 TRUE,  FALSE),
  (88,  'MINI PC',                        TRUE,  FALSE),
  (90,  'REPARACIONES',                   TRUE,  FALSE),
  (91,  'PULSERA ADULTO',                 TRUE,  FALSE),
  (92,  'RASTREADOR MASCOTAS',            TRUE,  FALSE),
  (199, 'SIN VALOR PARA INVENTARIO',      FALSE, FALSE),
  (200, 'Exportacion Web',                FALSE, FALSE),
  (201, 'Modelo Econométrico',            TRUE,  TRUE);

-- grupo_id con DEFAULT 201 transitorio: backfillea en el mismo ALTER las filas ya
-- existentes (hoy el 100% de los articulos en la base son del grupo 201, unico
-- procesado hasta ahora por el ETL). El DROP DEFAULT siguiente evita que un insert
-- futuro que se olvide de pasar grupo_id caiga silenciosamente en 201.
ALTER TABLE articulos
  ADD COLUMN grupo_id INT UNSIGNED NOT NULL DEFAULT 201 AFTER temporada_nombre,
  ADD CONSTRAINT fk_articulos_grupo FOREIGN KEY (grupo_id)
    REFERENCES grupos(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT;

ALTER TABLE articulos
  ALTER COLUMN grupo_id DROP DEFAULT;

CREATE INDEX idx_articulos_grupo_id ON articulos (grupo_id);
