// Issue #117: fuente unica para Rot. DesEstac. y DDSTK -- antes vivian
// duplicadas (exportPlanilla.ts y PlanillaTable.tsx tenian cada una su
// propia copia, ya divergidas del mismo bug), lo que dejaba abierta la
// puerta a que una se arreglara y la otra no.
import type { PlanillaMesDto } from '../types/planilla';

export const DDSTK_MIN_DIAS_CON_STOCK = 7;

/**
 * Rotación diaria promedio del año, corregida por estacionalidad, sobre los
 * meses cerrados (excluye siempre el último elemento del array = mes de
 * referencia en curso).
 *
 * Issue #117: un mes cuenta solo si hay factor estacional para calcular su
 * valor desestacionalizado -- normal usa rotacionDiariaDesestacionalizada
 * directo; quiebre_parcial la deriva (rotacionAjustada * desest/real) y
 * necesita las tres piezas presentes. Sin factor (rotacionDiariaDesestacio-
 * nalizada null) el mes se excluye, sea normal o quiebre_parcial -- antes
 * un quiebre_parcial sin factor caía a un valor sin corregir (rotacionAjus-
 * tada cruda), mezclando escalas en un promedio que se llama "desestacio-
 * nalizado". Si ningún mes tiene factor, el resultado es null (no un
 * promedio crudo bajo una etiqueta que promete corrección).
 */
export function calcularRotDesEstac(meses: PlanillaMesDto[]): number | null {
  const cerrados = meses.slice(0, -1);
  const vals: number[] = [];
  for (const m of cerrados) {
    if (m.estadoMes === 'normal' && m.rotacionDiariaDesestacionalizada != null) {
      vals.push(m.rotacionDiariaDesestacionalizada);
    } else if (
      m.estadoMes === 'quiebre_parcial' &&
      m.rotacionAjustada != null &&
      m.rotacionDiariaDesestacionalizada != null &&
      m.rotacionDiariaReal != null &&
      m.rotacionDiariaReal > 0
    ) {
      vals.push(m.rotacionAjustada * (m.rotacionDiariaDesestacionalizada / m.rotacionDiariaReal));
    }
  }
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
