# Archivos del cliente — septiembre 2026 (issue #195)

Dos archivos que Rodrigo Cabezas pasó el 2026-09-16, usados por
`scripts/cargador_archivos_cliente.py` como referencia del diagnóstico de
calidad de datos (#195 → #201). **No son entrada del pipeline** — son evidencia
congelada, no se regeneran.

Es la muestra más grande disponible hasta hoy: 5.428 SKUs, contra los ~1.100 de
los archivos parciales de #160/#161.

| Archivo | Original | Contenido |
|---|---|---|
| `ventas_hasta_2026-08_generos-todos.xlsx` | `Ventas hasta Mes 08-2026 - Generos Todos.xlsx` | Venta y rotación mensual de todo el catálogo, 13 meses Ago/25→Ago/26 |
| `mov_stock_deposito-5_2026-07.xlsx` | `Mov Stok Depo 5 Julio 2026.xlsx` | Movimientos de stock del depósito 5 en julio de 2026 |

## Archivo 1 — ventas

Hoja `Ventas`, 5.428 filas, 32 columnas. Mismo layout `bruto` que las planillas
de #127 (ver `../planillas_cliente/README.md`), pero con todos los géneros en
vez de un pedido:

| Columnas | Contenido |
|---|---|
| A–C | `Articulo` · `Descripcion` · `Codigos Barras` |
| D–P | `Vta.<mes>` — unidades vendidas, 13 meses |
| Q–AC | `<mes>` — rotación diaria del mes, 13 meses (sin prefijo, su convención) |
| AD | `Rotacion DesEstac.` |
| AE | `Rot. Manual` |
| AF | `Estado Art.` |

La ventana Ago/25→Ago/26 coincide exactamente con nuestra ventana rodante de 13
meses al momento de la entrega.

**La regla nulo/cero es asimétrica entre las dos familias de columnas**, y es la
trampa principal del archivo:

- Las columnas de **venta** usan celda vacía para "no vendió" y **nunca 0**: de
  70.564 celdas, 57.272 nulas (81%), **0 ceros explícitos**, 331 negativas,
  12.961 positivas. Los valores son enteros puros: son unidades, no importes.
- Las columnas de **rotación mensual** están **densas** — 70.564 valores, todas
  las celdas — y **sí usan cero explícito**.

Aplicar una sola regla a las dos familias genera miles de falsos positivos. Es
el problema de "cero implícito" de #187/#188, en espejo.

Otros números medidos: 4.719 `A` / 709 `D` en `Estado Art.`; 1.855 SKUs con al
menos un mes de venta; 1.419 con `Rotacion DesEstac.` cargada; sólo 1.679 (31%)
con código de barras, así que el barcode sirve como control secundario de
matcheo pero nunca como clave.

**`Rot. Manual` coincide con `Rotacion DesEstac.` en los 1.419 casos.** No es
una columna duplicada: el README de #127 documenta que `Rot. Manual` viene
precargada con `Rotacion DesEstac.` y que la persona que arma el pedido decide
activamente apartarse de ella. Que acá coincidan en todos los casos significa
que **este export no trae ninguna decisión experta cargada** — es un `bruto`.

## Archivo 2 — movimientos

Hoja `Sheet1`, 200 filas. **No es una tabla plana: es un reporte bandeado.** Un
parser que no filtre los artefactos triplica los totales — durante la
verificación del plan dio +1209/−2457/+1399 en vez de +403/−819/+466.

Lo que hay que filtrar:

- Filas de sección `Tipo de Documento: X` y `Genero: Y`, que hay que arrastrar
  como estado mientras se recorre.
- **35 filas de subtotal** con el literal `Total` en la primera columna.
- La fila `Total General`, con **las columnas corridas**: el total cae en la 2ª
  columna y en la 3ª y 4ª van los filtros del reporte.
- La fila `New Age Data` / `Pág.` / `1`, pie de página cuyo número de página cae
  en la columna de unidades y se ingiere como SKU fantasma.

Contenido real tras filtrar: **127 filas de detalle, 124 SKUs distintos**,
17 géneros, tres tipos de documento — Ajuste de Entrada +403, Ajuste de Salida
−819, Entrada de Mercadería +466 — y **neto +50**.

### Los filtros del reporte, impresos en `Total General`

```
Seccion: 0 a 99                 Art.: Activos - Inactivos - Disc.
Proveedor: 0 a 3048             Doc.: AJE,AJS,EMR,SMR,
Marca: 0 a 99                   NO Inc.Stk. Pendiente
Proveedor: Primario  -  Articulos: Importados y Plaza
Temporada: 0 a 2    Genero: 0 a 99
Clase: 0 a 99       Categoria: 0 a 99
Coleccion: Todos
```

**`Doc.: AJE,AJS,EMR,SMR` es una whitelist de tipos de documento**, y acota lo
que se puede concluir sobre #193. Que SMR haya vuelto vacío es evidencia a favor
de que no hubo remitos, pero **una transferencia entre depósitos con cualquier
otro código quedó excluida por el filtro, no por ausencia real**. Del archivo no
se puede deducir "no hay transferencias", sólo "no hay ninguno de los cuatro
tipos pedidos".

### Las Entradas de Mercadería son recodificación de SKU, no stock nuevo

**El 100% de las +466 unidades de Entrada de Mercadería es la contrapartida
exacta de 466 de las 819 unidades de Ajuste de Salida.** Son códigos que el
cliente retiró en julio y re-ingresó bajo otro SKU:

| Sale | | Entra | |
|---|---:|---|---:|
| `HX030` + `I01874` | −176 | `I01874` | +176 |
| `HX031` | −200 | `I02210` | +200 |
| `I01396` (cable X66 2MT) | −32 | `I02772` (cable X51 2MT) | +32 |
| `I01875` / `I01878` / `I01951` / `I02320` (repuestos "NO USAR") | −48 | `K00010` / `K00012` / `K00027` / `K00035` | +48 |
| `C00482` | −10 | `C00482` | +10 |
| | **−466** | | **+466** |

Hay además un par autocancelante dentro del mismo tipo de documento: `C00477`
con +50 de Ajuste de Entrada y −50 de Ajuste de Salida en el mismo mes, una
corrección de error.

Descontando la recodificación, la salida neta genuina es de **~353 unidades**.

Esto importa para la cobertura de catálogo: de los 124 SKUs, 121 están en
`articulos` y 3 no. Pero **`HX030` y `HX031` no son un hueco nuestro** — son
códigos de promo retirados cuyas unidades volvieron bajo `I01874` e `I02210`,
que sí tenemos. Entre los dos son 350 de las 819 unidades de Ajuste de Salida
(43%), así que reportarlos como ausencia nuestra sería el error más caro del
diagnóstico. La única ausencia real es **`I02045`** (+4 unidades, "CONTROL TV
BOX").

El emparejamiento lo hace `emparejar_recodificaciones()` por monto, sin lista
hardcodeada, desempatando por parecido de descripción — hay dos salidas de 14
unidades y sólo una es la contrapartida de `K00012`.

## Cobertura contra `articulos` (medida el 2026-09-16)

| | |
|---|---:|
| Artículos en `articulos` | 5.656 |
| SKUs del archivo de ventas | 5.428 |
| Comunes | **5.355** |
| Suyos que no tenemos | 73 |
| Nuestros que no están en su archivo | 301 |

Los 5.355 comunes son el conjunto sobre el que trabajan #196 en adelante: comparar
totales sin restringir a ese conjunto sesga el resultado, porque nuestro total
incluiría 301 artículos que ellos no mandaron.

Buena parte de los 73 ausentes son códigos `HX*`, la misma familia de promo que
`HX030`/`HX031`.

## Privacidad

Contienen ventas reales por artículo del cliente. El repositorio es privado; no
redistribuir estos archivos fuera de él.
