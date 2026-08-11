import { describe, expect, it } from 'vitest';
import type { PlanillaMesDto } from '../types/planilla';
import {
  DDSTK_MIN_DIAS_CON_STOCK,
  calcularDdstk,
  calcularRotDesEstac,
  celdaRotacionMes,
} from './planillaResumen';

function mes(overrides: Partial<PlanillaMesDto>): PlanillaMesDto {
  return {
    year: 2026,
    month: 5,
    ventasCantidad: 0,
    diasConStock: 30,
    diasNaturalesMes: 31,
    rotacionDiariaReal: null,
    rotacionDiariaBruta: null,
    rotacionDiariaDesestacionalizada: null,
    estadoMes: 'normal',
    frecuenciaNivel: null,
    rotacionAjustada: null,
    ticketsMes: 0,
    valorHistorico: null,
    valorAjustado: null,
    criterioFrecuencia: null,
    ...overrides,
  };
}

// El ultimo mes del array es siempre el mes de referencia (se excluye) --
// mismo contrato que exportPlanilla.ts / PlanillaTable.tsx.
function conReferencia(cerrados: PlanillaMesDto[]): PlanillaMesDto[] {
  return [...cerrados, mes({ year: 2026, month: 99, estadoMes: 'sin_datos' })];
}

describe('calcularRotDesEstac', () => {
  it('sin meses cerrados utilizables da null', () => {
    expect(calcularRotDesEstac(conReferencia([]))).toBeNull();
  });

  it('mes normal con factor participa con su valor desestacionalizado', () => {
    const meses = conReferencia([
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 4.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBe(3.0);
  });

  it('mes normal SIN factor (desestacionalizada null) se excluye', () => {
    const meses = conReferencia([
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: null }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 4.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBe(4.0);
  });

  it('quiebre_parcial con factor completo se corrige (ajustada * desest/real)', () => {
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 6.0,
        rotacionDiariaDesestacionalizada: 3.0,
        rotacionDiariaReal: 6.0,
      }),
    ]);
    // 6.0 * (3.0 / 6.0) = 3.0
    expect(calcularRotDesEstac(meses)).toBe(3.0);
  });

  it('issue #117: quiebre_parcial SIN factor estacional ya no mezcla escalas -- se excluye', () => {
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 6.0,
        rotacionDiariaDesestacionalizada: null, // sin factor
        rotacionDiariaReal: 6.0,
      }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
    ]);
    // Si el quiebre sin factor mezclara (bug viejo): (6.0 + 2.0) / 2 = 4.0
    // Con el fix, el quiebre sin factor se excluye: solo participa el normal.
    expect(calcularRotDesEstac(meses)).toBe(2.0);
  });

  it('issue #117: SKU sin ningun factor estacional da null, no un promedio crudo', () => {
    const meses = conReferencia([
      mes({ estadoMes: 'quiebre_parcial', rotacionAjustada: 6.0, rotacionDiariaDesestacionalizada: null, rotacionDiariaReal: 6.0 }),
      mes({ estadoMes: 'quiebre_parcial', rotacionAjustada: 4.0, rotacionDiariaDesestacionalizada: null, rotacionDiariaReal: 4.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBeNull();
  });

  it('quiebre_parcial con rotacionDiariaReal en 0 tambien se excluye (no se puede derivar el factor)', () => {
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 6.0,
        rotacionDiariaDesestacionalizada: 3.0,
        rotacionDiariaReal: 0,
      }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBe(2.0);
  });

  it('sin_stock y sin_datos no participan', () => {
    const meses = conReferencia([
      mes({ estadoMes: 'sin_stock', rotacionDiariaDesestacionalizada: null }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 5.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBe(5.0);
  });

  it('el mes de referencia (ultimo del array) siempre se excluye', () => {
    const meses = [
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 999.0 }), // referencia
    ];
    expect(calcularRotDesEstac(meses)).toBe(2.0);
  });
});

describe('calcularDdstk', () => {
  it('sin ningun dia con stock da null', () => {
    const meses = [mes({ diasConStock: 0, ventasCantidad: 0 })];
    expect(calcularDdstk(meses)).toBeNull();
  });

  it('con dias con stock por encima del umbral calcula normal', () => {
    const meses = [mes({ diasConStock: 30, ventasCantidad: 60 })];
    expect(calcularDdstk(meses)).toBe(2.0);
  });

  it('issue #117: por debajo del umbral minimo de dias con stock da null, no un numero enganoso', () => {
    const meses = [mes({ diasConStock: DDSTK_MIN_DIAS_CON_STOCK - 1, ventasCantidad: 100 })];
    expect(calcularDdstk(meses)).toBeNull();
  });

  it('issue #117: el umbral minimo es inclusive', () => {
    const meses = [mes({ diasConStock: DDSTK_MIN_DIAS_CON_STOCK, ventasCantidad: 14 })];
    expect(calcularDdstk(meses)).not.toBeNull();
  });

  it('suma dias con stock y ventas de todos los meses, incluido el de referencia', () => {
    const meses = [
      mes({ diasConStock: 5, ventasCantidad: 10 }),
      mes({ diasConStock: 5, ventasCantidad: 10 }), // "de referencia", igual participa en DDSTK
    ];
    expect(calcularDdstk(meses)).toBe(2.0);
  });
});

// ── celdaRotacionMes — issue #130 ────────────────────────────────────────────
// Las columnas mensuales pasan a mostrar la rotación desestacionalizada, que es
// lo que promedia la columna resumen: hasta ahora mostraban la cruda, así que
// el resumen no se podía reproducir con los números visibles. El estado que
// devuelve esta función es el que decide el color de la celda.

describe('celdaRotacionMes', () => {
  it('mes normal con factor: muestra el valor desestacionalizado', () => {
    const c = celdaRotacionMes(mes({ estadoMes: 'normal', rotacionDiariaReal: 4, rotacionDiariaDesestacionalizada: 2 }));
    expect(c).toEqual({ valor: 2, estado: 'normal' });
  });

  it('el valor mostrado es el que promedia la columna resumen, no la rotación cruda', () => {
    const m = mes({ estadoMes: 'normal', rotacionDiariaReal: 4, rotacionDiariaDesestacionalizada: 2 });
    expect(celdaRotacionMes(m).valor).toBe(calcularRotDesEstac(conReferencia([m])));
  });

  it('issue #130: mes con stock y ventas pero SIN factor estacional queda vacío y marcado', () => {
    // 1784 celdas de producción caen acá. Antes mostraban la rotación cruda y
    // se pintaban como un mes normal cualquiera; el color nuevo explica el hueco.
    const c = celdaRotacionMes(mes({ estadoMes: 'normal', rotacionDiariaReal: 4, rotacionDiariaDesestacionalizada: null }));
    expect(c).toEqual({ valor: null, estado: 'sin_factor' });
  });

  it('quiebre con factor: valor corregido y estado de quiebre para conservar el color', () => {
    // ajustada != real a propósito: son el único par de valores que distingue
    // la fórmula del promedio de la del valor crudo desestacionalizado. Con
    // ajustada == real las dos coinciden y el test no probaría nada.
    const c = celdaRotacionMes(mes({
      estadoMes: 'quiebre_parcial', frecuenciaNivel: 'media',
      rotacionDiariaReal: 2, rotacionAjustada: 2.2, rotacionDiariaDesestacionalizada: 1,
    }));
    expect(c.valor).toBeCloseTo(1.1, 10);   // 2.2 * (1/2), no el 1.0 de la desest cruda
    expect(c.estado).toBe('quiebre_parcial');
  });

  it('issue #130: la celda de un mes con quiebre muestra EXACTAMENTE lo que promedia el resumen', () => {
    // Es la razón de ser del ticket. Si la celda y el promedio se calculan por
    // caminos separados, el cliente no puede verificar la cuenta -- que es el
    // problema original. Un solo mes cerrado => promedio == valor de la celda.
    const quiebre = mes({
      estadoMes: 'quiebre_parcial',
      rotacionDiariaReal: 2, rotacionAjustada: 2.2, rotacionDiariaDesestacionalizada: 1,
    });
    expect(celdaRotacionMes(quiebre).valor).toBe(calcularRotDesEstac(conReferencia([quiebre])));
  });

  it('issue #130: lo mismo para un mes normal', () => {
    const normal = mes({ estadoMes: 'normal', rotacionDiariaReal: 4, rotacionDiariaDesestacionalizada: 2 });
    expect(celdaRotacionMes(normal).valor).toBe(calcularRotDesEstac(conReferencia([normal])));
  });

  it('quiebre sin rotación real > 0 no es derivable: celda vacía y fuera del promedio', () => {
    // El promedio ya lo excluía (#117, no se puede derivar el factor con real=0).
    // La celda tiene que coincidir, o vuelve a mostrarse algo que el resumen ignora.
    const m = mes({
      estadoMes: 'quiebre_parcial',
      rotacionDiariaReal: 0, rotacionAjustada: 3, rotacionDiariaDesestacionalizada: 0,
    });
    expect(celdaRotacionMes(m)).toEqual({ valor: null, estado: 'sin_factor' });
    expect(calcularRotDesEstac(conReferencia([m]))).toBeNull();
  });

  it('quiebre sin factor: también queda vacío y marcado como sin_factor', () => {
    const c = celdaRotacionMes(mes({
      estadoMes: 'quiebre_parcial', rotacionAjustada: 6, rotacionDiariaDesestacionalizada: null,
    }));
    expect(c).toEqual({ valor: null, estado: 'sin_factor' });
  });

  it('sin_stock queda vacío conservando su propio estado, no se confunde con sin_factor', () => {
    const c = celdaRotacionMes(mes({ estadoMes: 'sin_stock', rotacionDiariaReal: 0, rotacionDiariaDesestacionalizada: null }));
    expect(c).toEqual({ valor: null, estado: 'sin_stock' });
  });

  it('sin_datos queda vacío conservando su propio estado', () => {
    const c = celdaRotacionMes(mes({ estadoMes: 'sin_datos', rotacionDiariaReal: null, rotacionDiariaDesestacionalizada: null }));
    expect(c).toEqual({ valor: null, estado: 'sin_datos' });
  });

  it('una rotación desestacionalizada de 0 es un dato real, no un hueco', () => {
    const c = celdaRotacionMes(mes({ estadoMes: 'normal', rotacionDiariaReal: 0, rotacionDiariaDesestacionalizada: 0 }));
    expect(c).toEqual({ valor: 0, estado: 'normal' });
  });
});
