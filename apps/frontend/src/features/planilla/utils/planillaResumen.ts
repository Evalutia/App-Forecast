// Issue #117: fuente unica para Rot. DesEstac. y DDSTK -- antes vivian
// duplicadas (exportPlanilla.ts y PlanillaTable.tsx tenian cada una su
// propia copia, ya divergidas del mismo bug), lo que dejaba abierta la
// puerta a que una se arreglara y la otra no.
import type { PlanillaMesDto } from '../types/planilla';

export const DDSTK_MIN_DIAS_CON_STOCK = 7;

/**
 * Estado de una celda mensual de rotación, a efectos de qué color le
 * corresponde. Los cuatro primeros son los estados del mes que ya existían;
 * `sin_factor` es nuevo (issue #130).
 */
export type EstadoCeldaRotacion =
  | 'normal'
  | 'quiebre_parcial'
  | 'sin_stock'
  | 'sin_datos'
  | 'sin_factor';

/**
 * Qué mostrar y cómo pintar una celda mensual de rotación.
 *
 * Issue #130: estas columnas mostraban la rotación **cruda** mientras la
 * columna resumen `Rotacion DesEstac.` promedia los valores
 * **desestacionalizados** -- o sea que el cliente no podía reproducir el
 * resumen con los números que tenía al lado. Ahora muestran lo mismo que el
 * resumen promedia.
 *
 * El cambio deja un caso que antes no existía: un mes con stock y ventas pero
 * sin rotación corregida derivable -- casi siempre porque al artículo le falta
 * el factor estacional de ese mes, de ahí el nombre del estado. Son ~1.784
 * celdas en producción (9,2% de las que hoy muestran un número). Se devuelven
 * con estado propio `sin_factor` para que el color explique el hueco en vez de
 * dejarlo mudo: pintarlas como un mes normal sería peor que antes, porque el
 * cliente vería una celda vacía sin motivo aparente.
 *
 * El resto conserva su estado, y con él su color: la señal de quiebre sigue
 * siendo información útil aunque el valor ya esté corregido.
 *
 * Issue #134: `sin_factor` queda reservado para cuando de verdad falta el
 * factor estacional (`rotacionDiariaDesestacionalizada` null). Antes también
 * se disparaba para meses `quiebre_parcial` con venta real 0 -- un efecto
 * secundario del guard `rotacionDiariaReal > 0` que `rotacionDesestacionalizadaMes`
 * ya no aplica -- y esa celda mentía: el factor sí estaba cargado, solo que
 * el mes no vendió nada.
 */
/**
 * Issue #179: si el último mes de la ventana es realmente el mes calendario
 * actual, esta señal decide si corresponde tratarlo como "en curso,
 * incompleto" -- en vez de asumir POSICIONALMENTE que el último elemento del
 * array siempre lo es. La ventana viene de `GetVentanaMeses` (MIN/MAX de
 * `planilla_ventas_calculada`), que solo refleja hasta donde el ETL corrió
 * anoche. Si el cron todavía no escribió el mes calendario nuevo (la
 * ventana horaria entre medianoche y que termine la corrida nocturna, TODOS
 * los meses) o si el ETL se atrasó varias noches (confirmado históricamente
 * contra `jobs_historial`: el incidente de #111, 23/07→02/08/2026, dejó la
 * ventana varada en julio -- ya cerrado -- durante los primeros días de
 * agosto), el último elemento del array es en realidad un mes YA CERRADO, y
 * tratarlo como "en curso" lo excluía en silencio de VTA/Rot.DesEstac.
 *
 * `hoy` inyectable para tests, default `new Date()` -- alcanza el reloj del
 * cliente, la comparación es a granularidad de mes, no de milisegundos.
 */
export function esMesEnCursoReal(
  mes: { year: number; month: number } | undefined,
  hoy: Date = new Date(),
): boolean {
  if (!mes) return false;
  return mes.year === hoy.getFullYear() && mes.month === hoy.getMonth() + 1;
}

export function celdaRotacionMes(
  mes: PlanillaMesDto,
): { valor: number | null; estado: EstadoCeldaRotacion } {
  if (mes.estadoMes === 'sin_datos' || mes.estadoMes === 'sin_stock') {
    return { valor: null, estado: mes.estadoMes };
  }
  const valor = rotacionDesestacionalizadaMes(mes);
  // El estado 'sin_factor' gana sobre el de quiebre a propósito: la celda está
  // vacía, y sobre una celda vacía el color de quiebre no contextualiza ningún
  // número -- explicar el hueco es más útil. La señal de quiebre no se pierde
  // de la fila: la columna de venta del mismo mes la conserva.
  return valor == null
    ? { valor: null, estado: 'sin_factor' }
    : { valor, estado: mes.estadoMes };
}

/**
 * Rotación diaria promedio del año, corregida por estacionalidad, sobre los
 * meses cerrados -- excluye el último elemento del array SOLO si de verdad
 * es el mes calendario en curso (#179, ver `esMesEnCursoReal` y el
 * docstring de `calcularRotDesEstac`, que consume esta función).
 *
 * Promedia exactamente los valores que `rotacionDesestacionalizadaMes`
 * devuelve para cada mes -- que son los mismos que muestran las columnas
 * mensuales (#130). Si esas dos cosas se calcularan por separado, el cliente
 * no podría reproducir este promedio con los números que tiene al lado, que
 * es justamente el problema que #130 vino a resolver.
 *
 * Si ningún mes aporta valor, el resultado es null (no un promedio crudo bajo
 * una etiqueta que promete corrección) -- ver #117.
 */
export function rotacionDesestacionalizadaMes(m: PlanillaMesDto): number | null {
  if (m.estadoMes === 'normal') {
    return m.rotacionDiariaDesestacionalizada;
  }
  if (m.estadoMes !== 'quiebre_parcial' || m.rotacionDiariaDesestacionalizada == null) {
    return null;
  }
  // Issue #134: con venta real 0 no hace falta derivar el factor por
  // cociente -- el ETL ya persiste la desestacionalizada en 0 (0 ÷ cualquier
  // factor da 0), así que el mes participa con ese valor real en vez de
  // descartarse. Mismo criterio que #116 ya fijó para ROT.S: un mes cerrado
  // sin ventas es un dato real, no un hueco. El guard viejo (`> 0`) tiraba
  // estos meses aunque el valor ya estuviera disponible y fuera correcto --
  // el sesgo iba siempre hacia arriba (se descartaban los meses malos, nunca
  // los buenos).
  if (m.rotacionDiariaReal === 0) {
    return m.rotacionDiariaDesestacionalizada;
  }
  // rotacionDiariaReal < 0 (devoluciones netas superando la venta del mes,
  // posible desde #80) sigue excluido: dividir por un real negativo daría una
  // "rotación corregida" negativa sin sentido, y el bug que #134 vino a
  // arreglar era el descarte de un 0 real, no el de un real negativo.
  if (m.rotacionAjustada != null && m.rotacionDiariaReal != null && m.rotacionDiariaReal > 0) {
    return m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal);
  }
  return null;
}

/**
 * Issue #179: el último mes de `meses` solo se excluye si `esMesEnCursoReal`
 * confirma que es de verdad el mes calendario actual -- ya no se asume por
 * posición. Ver el docstring de `esMesEnCursoReal` para el mecanismo
 * completo (por qué el último elemento puede ser un mes ya cerrado).
 */
export function calcularRotDesEstac(meses: PlanillaMesDto[], hoy: Date = new Date()): number | null {
  const cerrados = esMesEnCursoReal(meses[meses.length - 1], hoy) ? meses.slice(0, -1) : meses;
  const vals = cerrados
    .map(rotacionDesestacionalizadaMes)
    .filter((v): v is number => v != null);
  return vals.length === 0 ? null : vals.reduce((s, v) => s + v, 0) / vals.length;
}

/**
 * Demanda Diaria con Stock: venta promedio por día en los días que hubo
 * stock, sobre la ventana completa (incluye el mes de referencia).
 *
 * Issue #117: por debajo de DDSTK_MIN_DIAS_CON_STOCK días con stock en toda
 * la ventana, el denominador es demasiado chico para confiar en el
 * resultado (un puñado de ventas sobre 1-2 días puede dar una demanda
 * diaria de dos dígitos sin ninguna marca de que se calculó sobre casi
 * nada) -- se prefiere vacío a un número engañoso, mismo criterio que ya
 * usan ROT.S (mínimo de meses) y QBK (máximo de antigüedad del stock).
 *
 * Issue #134: el numerador solo suma la venta de los meses que también
 * aportan al denominador (`diasConStock > 0`). Antes sumaba los 13 meses
 * sin filtrar, así que un mes sin ningún día de stock aportaba venta pero no
 * días, inflando el resultado -- la columna se define como "venta promedio
 * por día en los días que hubo stock", no "venta total ÷ días con stock de
 * otros meses".
 */
export function calcularDdstk(meses: PlanillaMesDto[]): number | null {
  const mesesConStock = meses.filter((m) => (m.diasConStock ?? 0) > 0);
  const totalVentas = mesesConStock.reduce((s, m) => s + (m.ventasCantidad ?? 0), 0);
  const totalDias = mesesConStock.reduce((s, m) => s + (m.diasConStock ?? 0), 0);
  if (totalDias < DDSTK_MIN_DIAS_CON_STOCK) return null;
  return totalVentas / totalDias;
}

/**
 * Redondea QBK (días hasta quiebre) para mostrar, sin exagerar la urgencia
 * por redondeo (issue #143). `diasHastaQuiebre` viene del backend como
 * `stock_actual / rotacion_sugerida`, siempre >= 0 -- un artículo con 0.4
 * días de cobertura real (todavía tiene stock) redondeaba a 0 con
 * `Math.round`, y la hoja "Criterios" dice "0 = ya sin stock": sobre-reporta
 * urgencia justo en el borde. Cualquier valor > 0 se muestra como mínimo 1;
 * solo un valor exactamente 0 (stock_actual en 0, clampeado en el backend)
 * se muestra como 0. Fuente única -- antes cada archivo redondeaba por su
 * cuenta con `Math.round`, mismo patrón divergente que #117 documenta para
 * DDSTK/Rot.DesEstac.
 */
export function redondearDiasQuiebre(dias: number): number {
  return dias > 0 ? Math.max(1, Math.round(dias)) : 0;
}

/**
 * Redondea la fiabilidad (%) para mostrar, fuente única para web y Excel
 * (issue #169, mismo patrón que #143 fijó arriba para QBK).
 *
 * Antes, `fiabilidadClass` en PlanillaTable.tsx clasificaba los umbrales
 * 70/40 sobre el valor CRUDO mientras el texto mostraba `toFixed(0)`
 * (redondeado) -- el badge de color y el número que lee el cliente podían
 * contradecirse en el borde. Casos reales:
 *   - C00679 (69,75 crudo): el texto mostraba "70%", pero el badge daba
 *     AMARILLO (69,75 < 70 crudo) -- contradice al propio número mostrado.
 *   - T00145E (39,99 crudo): el texto mostraba "40%", pero el badge daba
 *     ROJO (39,99 < 40 crudo) -- 40% cae en la banda Amarillo (40-69%) que
 *     la leyenda promete, no en Rojo.
 *
 * El fix: un solo redondeo (`Math.round`, sin piso especial -- a diferencia
 * de `redondearDiasQuiebre`, acá 0% es un valor válido que no hay que
 * proteger de aterrizar en 0), y tanto el texto como `fiabilidadClass`
 * clasifican sobre ESTE valor ya redondeado, nunca sobre el crudo. Con el
 * fix, C00679 pasa a badge VERDE (70 >= 70) -- un cambio real de color,
 * ahora coherente con el "70%" que siempre mostró el texto.
 */
export function redondearFiabilidad(pct: number): number {
  return Math.round(pct);
}

/**
 * VTA: suma de `ventasCantidad` de los meses cerrados -- excluye el último
 * elemento del array solo si `esMesEnCursoReal` confirma que es de verdad
 * el mes calendario en curso (#179), mismo contrato que `calcularRotDesEstac`.
 *
 * Issue #171: `PlanillaTable.tsx` y `exportPlanilla.ts` reimplementaban esta
 * misma expresión cada uno por su lado -- carácter por carácter idénticas al
 * momento de este ticket, sin divergencia numérica todavía, pero exactamente
 * la forma que #117 y #129 tenían antes de divergir de verdad en este mismo
 * código. Fuente única para que arreglar una implique arreglar la otra.
 */
export function calcularVta(meses: PlanillaMesDto[], hoy: Date = new Date()): number {
  const cerrados = esMesEnCursoReal(meses[meses.length - 1], hoy) ? meses.slice(0, -1) : meses;
  return cerrados.reduce((s, m) => s + (m.ventasCantidad ?? 0), 0);
}
