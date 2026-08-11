# Planillas de reposición del cliente (issue #127)

Seis archivos enviados por el cliente el 2026-08-09, usados por
`scripts/diagnostico_planillas_cliente.py` como referencia contra la cual
contrastar lo que calculamos nosotros. **No son entrada del pipeline** — son
evidencia congelada, no se regeneran.

Son tres pedidos, cada uno en dos versiones:

| Pedido | `bruto` | `rot-ok` |
|---|---|---|
| FANTECH, mes 11-2026 | `fantech_2026-11_bruto.xlsx` | `fantech_2026-11_rot-ok.xlsm` |
| FONENG (auriculares), mes 11-2026 | `foneng-auricular_2026-11_bruto.xlsx` | `foneng-auricular_2026-11_rot-ok.xlsm` |
| TONER CPT, mes 10-2026 | `toner-cpt_2026-10_bruto.xlsx` | `toner-cpt_2026-10_rot-ok.xlsx` |

Palabras del cliente: *"las que fueron nombradas con la palabra BRUTO son las
que emite el sistema; las denominadas ROT OK son las que tienen la rotación
diaria desestacionalizada elegida para ese pedido, columna AE de la hoja
Ventas"*.

## Layout de la hoja `Ventas`

| Columnas | Contenido |
|---|---|
| A–C | Artículo · Descripción · Códigos de barras |
| D–P | `Vta.<mes>` — unidades vendidas, 13 meses |
| Q–AC | `<mes>` — rotación diaria del mes, 13 meses (sin prefijo, su convención) |
| AD | `Rotacion DesEstac.` |
| AE | `Rot. Manual` |
| AF | `Estado Art.` |
| AG–AL | **sólo en los `rot-ok`**: `SIN STOCK` · `SIN STOCK` · `TOT STK` · `C/STK` · `VTA` · `DDSTK` |

Precisiones que sólo se ven abriendo las fórmulas, y que motivaron #127:

- **`AE` no es lo que dice el mail.** Se llama `Rot. Manual`, no "rotación
  desestacionalizada" (esa es `AD`). Su fórmula es siempre
  `=AVERAGE(<inicio>:<último mes cerrado>)`: promedio simple que **termina
  siempre en el último mes cerrado** pero cuyo **inicio elige la persona que
  arma el pedido** — 7 meses en FANTECH y TONER, 6 en FONENG, casos sueltos de
  8, 5 y 3, más ~130 valores escritos a mano.
- **`AD` es el promedio simple de los 12 meses cerrados contando los ceros**,
  el mismo criterio que adoptamos por separado en #116 y #117.
- **El default de `Rot. Manual` es `Rotacion DesEstac.`** En los `bruto` la
  columna viene precargada en 521 filas y en **todas** coincide exactamente con
  `AD`. O sea que el sistema propone su propia rotación y la persona que arma
  el pedido decide activamente apartarse de ella — el desvío experto medible es
  `rot-ok` menos `bruto`, no `rot-ok` a secas.
- **El bloque AG–AL de los `rot-ok` es evidencia directa del denominador**, y
  se pasó por alto en la primera lectura de #127 (que llegó a afirmar que sus
  archivos no traían los días con stock — es cierto sólo para los `bruto`).
  `C/STK` son los días con stock sobre una ventana de **360 días**
  (`C/STK = 360 − TOT STK`) y `DDSTK = VTA / C/STK` se cumple exacto en el
  100% de los SKUs con datos: **su demanda diaria divide por días con
  stock**, igual que la nuestra.

La hoja `Compras` de cada archivo arma el pedido a partir de `AE`. Está fuera
de alcance como producto (#33, ratificado en #107); acá interesa sólo como
contexto: multiplica la rotación por **días de calendario**.

## Privacidad

Contienen ventas reales por artículo del cliente. El repositorio es privado;
no redistribuir estos archivos fuera de él.
