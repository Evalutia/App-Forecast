import { describe, expect, it } from 'vitest';
import type { PlanillaMesDto } from '../types/planilla';
import { DDSTK_MIN_DIAS_CON_STOCK, calcularDdstk, calcularRotDesEstac } from './planillaResumen';

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
