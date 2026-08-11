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
 */
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
 * meses cerrados (excluye siempre el último elemento del array = mes de
 * referencia en curso).
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
  if (
    m.estadoMes === 'quiebre_parcial' &&
    m.rotacionAjustada != null &&
    m.rotacionDiariaDesestacionalizada != null &&
    m.rotacionDiariaReal != null &&
    m.rotacionDiariaReal > 0
  ) {
    return m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal);
  }
  return null;
}

export function calcularRotDesEstac(meses: PlanillaMesDto[]): number | null {
  const vals = meses
    .slice(0, -1)
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
 */
export function calcularDdstk(meses: PlanillaMesDto[]): number | null {
  const totalVentas = meses.reduce((s, m) => s + (m.ventasCantidad ?? 0), 0);
  const totalDias = meses.reduce((s, m) => s + (m.diasConStock ?? 0), 0);
  if (totalDias < DDSTK_MIN_DIAS_CON_STOCK) return null;
  return totalVentas / totalDias;
}
