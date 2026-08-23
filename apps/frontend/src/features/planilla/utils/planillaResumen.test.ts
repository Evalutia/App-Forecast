import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { PlanillaMesDto } from '../types/planilla';
import {
  DDSTK_MIN_DIAS_CON_STOCK,
  calcularDdstk,
  calcularRotDesEstac,
  calcularVta,
  celdaRotacionMes,
  esMesEnCursoReal,
  redondearDiasQuiebre,
  redondearFiabilidad,
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
    ventaOExtrapolacion: null,
    ingresoDuranteQuiebre: false,
    ...overrides,
  };
}

// Issue #179: calcularVta/calcularRotDesEstac ya no excluyen el último mes
// del array por posición -- solo si esMesEnCursoReal confirma que es de
// verdad el mes calendario actual. El "reloj" del test se congela más abajo
// (beforeAll/afterAll) en 2026-06-15 para que este mes de referencia siga
// jugando su mismo rol de siempre en toda la suite, sin tocar los ~18 call
// sites existentes.
const HOY_TEST = new Date(2026, 5, 15); // mes 5 = junio (0-indexado)

beforeAll(() => {
  vi.useFakeTimers();
  vi.setSystemTime(HOY_TEST);
});

afterAll(() => {
  vi.useRealTimers();
});

function conReferencia(cerrados: PlanillaMesDto[]): PlanillaMesDto[] {
  return [...cerrados, mes({ year: 2026, month: 6, estadoMes: 'sin_datos' })];
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

  it('issue #134: quiebre_parcial con rotacionDiariaReal en 0 participa con la desestacionalizada, no se descarta', () => {
    // Con venta real 0 no hace falta derivar por cociente: el mes participa
    // con el valor que el ETL ya persiste, aunque no sea 0 en este caso de
    // prueba (el fix no asume ningún valor puntual, usa el que venga).
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 6.0,
        rotacionDiariaDesestacionalizada: 3.0,
        rotacionDiariaReal: 0,
      }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
    ]);
    // Bug viejo (guard `> 0`): el quiebre se descartaba -> (2.0)/1 = 2.0
    // Fix: el quiebre participa con su desestacionalizada -> (3.0 + 2.0) / 2 = 2.5
    expect(calcularRotDesEstac(meses)).toBe(2.5);
  });

  it('issue #134: quiebre_parcial con rotacionDiariaReal NEGATIVO se sigue excluyendo, no se divide por negativo', () => {
    // Devoluciones netas superando la venta del mes (posible desde #80) dan
    // rotacionDiariaReal < 0. El fix de #134 es específico para el 0 -- un
    // real negativo no tiene una "rotación corregida" con sentido, así que
    // el mes se sigue descartando, igual que antes de este ticket.
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 6.0,
        rotacionDiariaDesestacionalizada: 3.0,
        rotacionDiariaReal: -2,
      }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 4.0 }),
    ]);
    // Si dividiera por el real negativo: 6.0 * (3.0 / -2) = -9.0, promedio -2.5 (sin sentido).
    // Con el mes excluido, solo participa el normal.
    expect(calcularRotDesEstac(meses)).toBe(4.0);
  });

  it('issue #134: mes de quiebre con venta 0 real (caso O00847) participa con rotación 0, no se descarta', () => {
    // Caso real del ETL: con ventasCantidad=0 y dias_con_stock>0, rot_real=0 y
    // rot_desest=round(0/factor,4)=0 -- el ETL persiste un 0 real, no un null.
    const meses = conReferencia([
      mes({
        estadoMes: 'quiebre_parcial',
        rotacionAjustada: 3.0,
        rotacionDiariaDesestacionalizada: 0,
        rotacionDiariaReal: 0,
      }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 4.0 }),
    ]);
    // Bug viejo: se descartaba -> 4.0. Fix: participa con 0 -> (0 + 4.0)/2 = 2.0
    expect(calcularRotDesEstac(meses)).toBe(2.0);
  });

  it('sin_stock y sin_datos no participan', () => {
    const meses = conReferencia([
      mes({ estadoMes: 'sin_stock', rotacionDiariaDesestacionalizada: null }),
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 5.0 }),
    ]);
    expect(calcularRotDesEstac(meses)).toBe(5.0);
  });

  it('el mes de referencia (ultimo del array) se excluye si es de verdad el mes en curso', () => {
    const meses = [
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 2.0 }),
      mes({ year: 2026, month: 6, estadoMes: 'normal', rotacionDiariaDesestacionalizada: 999.0 }), // referencia -- coincide con HOY_TEST
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

  it('issue #134: ventas de un mes sin ningun dia con stock no inflan el numerador', () => {
    const meses = [
      mes({ diasConStock: 10, ventasCantidad: 20 }),
      mes({ diasConStock: 0, ventasCantidad: 50 }), // vendió pese a no tener dias con stock ese mes
    ];
    // Bug viejo: (20 + 50) / 10 = 7. Fix: el mes sin stock no aporta al numerador -> 20 / 10 = 2.
    expect(calcularDdstk(meses)).toBe(2.0);
  });

  it('issue #134: si TODOS los meses con venta estan sin dias de stock, el numerador queda en 0', () => {
    const meses = [
      mes({ diasConStock: 10, ventasCantidad: 0 }),
      mes({ diasConStock: 0, ventasCantidad: 50 }),
    ];
    expect(calcularDdstk(meses)).toBe(0);
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

  it('issue #134: quiebre con venta real 0 pero factor cargado muestra 0, no cae en sin_factor', () => {
    // Antes (#130/bug viejo): el guard `rotacionDiariaReal > 0` volvía la celda
    // 'sin_factor' aunque el factor estuviera cargado -- el lila mentía. La
    // celda tiene que coincidir con lo que ahora promedia calcularRotDesEstac.
    const m = mes({
      estadoMes: 'quiebre_parcial',
      rotacionDiariaReal: 0, rotacionAjustada: 3, rotacionDiariaDesestacionalizada: 0,
    });
    expect(celdaRotacionMes(m)).toEqual({ valor: 0, estado: 'quiebre_parcial' });
    expect(calcularRotDesEstac(conReferencia([m]))).toBe(0);
  });

  it('quiebre sin factor: también queda vacío y marcado como sin_factor', () => {
    const c = celdaRotacionMes(mes({
      estadoMes: 'quiebre_parcial', rotacionAjustada: 6, rotacionDiariaDesestacionalizada: null,
    }));
    expect(c).toEqual({ valor: null, estado: 'sin_factor' });
  });

  it('issue #134: quiebre con venta real 0 Y sin factor cargado sigue siendo sin_factor (falta de verdad)', () => {
    // sin_factor tiene que quedar reservado para cuando el factor realmente
    // no está -- no puede volver a dispararse como efecto secundario del
    // valor de rotacionDiariaReal.
    const c = celdaRotacionMes(mes({
      estadoMes: 'quiebre_parcial', rotacionDiariaReal: 0, rotacionAjustada: 6, rotacionDiariaDesestacionalizada: null,
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

describe('redondearDiasQuiebre', () => {
  it('issue #143: un valor positivo que redondearía a 0 se muestra como 1, no como "ya sin stock"', () => {
    expect(redondearDiasQuiebre(0.4)).toBe(1);
    expect(redondearDiasQuiebre(0.01)).toBe(1);
  });

  it('exactamente 0 se muestra como 0 (ya sin stock, dato real)', () => {
    expect(redondearDiasQuiebre(0)).toBe(0);
  });

  it('valores que ya redondeaban a 1 o más no cambian de comportamiento', () => {
    expect(redondearDiasQuiebre(0.5)).toBe(1);
    expect(redondearDiasQuiebre(1.4)).toBe(1);
    expect(redondearDiasQuiebre(15.2)).toBe(15);
    expect(redondearDiasQuiebre(15.5)).toBe(16);
  });
});

// ── redondearFiabilidad — issue #169 ─────────────────────────────────────────
// Mismo patrón que #143 fijó arriba para redondearDiasQuiebre: un solo
// redondeo, fuente de verdad compartida por PlanillaTable.tsx (texto +
// fiabilidadClass) y exportPlanilla.ts, para que el badge de color nunca
// contradiga el número que el cliente lee.

describe('redondearFiabilidad', () => {
  it('redondea al entero más cercano, sin piso especial (0% es un valor válido)', () => {
    expect(redondearFiabilidad(0)).toBe(0);
    expect(redondearFiabilidad(0.4)).toBe(0);
    expect(redondearFiabilidad(100)).toBe(100);
  });

  it('valor exactamente en el borde de 70 (69,5 redondea a 70)', () => {
    expect(redondearFiabilidad(69.5)).toBe(70);
  });

  it('valor exactamente en el borde de 40 (39,5 redondea a 40)', () => {
    expect(redondearFiabilidad(39.5)).toBe(40);
  });

  it('caso real C00679 (69,75 crudo) redondea a 70', () => {
    expect(redondearFiabilidad(69.75)).toBe(70);
  });

  it('caso real T00145E (39,99 crudo) redondea a 40', () => {
    expect(redondearFiabilidad(39.99)).toBe(40);
  });
});

// ── fiabilidadClass sobre el valor YA redondeado — issue #169 ───────────────
// `fiabilidadClass` vive en PlanillaTable.tsx (se exporta ahí para este
// test); acá se verifica la composición completa redondearFiabilidad() ->
// fiabilidadClass(), que es exactamente lo que hace AeCell para decidir el
// texto y el color del badge con el MISMO valor.

// ── calcularVta — issue #171 ─────────────────────────────────────────────────
// PlanillaTable.tsx y exportPlanilla.ts reimplementaban esta misma suma cada
// uno por su lado (carácter por carácter idénticas al momento del ticket) --
// exactamente la forma que #117 y #129 tenían antes de divergir de verdad.

describe('calcularVta', () => {
  it('suma ventasCantidad de los meses cerrados, excluyendo el mes de referencia', () => {
    const meses = conReferencia([
      mes({ ventasCantidad: 10 }),
      mes({ ventasCantidad: 20 }),
    ]);
    expect(calcularVta(meses)).toBe(30);
  });

  it('el mes de referencia (ultimo del array) no participa en la suma si es de verdad el mes en curso', () => {
    const meses = [
      mes({ ventasCantidad: 5 }),
      mes({ year: 2026, month: 6, ventasCantidad: 999 }), // referencia -- coincide con HOY_TEST
    ];
    expect(calcularVta(meses)).toBe(5);
  });

  it('ventasCantidad ausente (null/undefined) suma como 0, no rompe ni descarta la fila', () => {
    const meses = conReferencia([
      mes({ ventasCantidad: 10 }),
      mes({ ventasCantidad: null as unknown as number }),
    ]);
    expect(calcularVta(meses)).toBe(10);
  });

  it('sin meses cerrados (solo el de referencia) da 0', () => {
    expect(calcularVta(conReferencia([]))).toBe(0);
  });
});

describe('esMesEnCursoReal (#179)', () => {
  it('true cuando el mes coincide con el calendario real (año y mes)', () => {
    expect(esMesEnCursoReal({ year: 2026, month: 6 }, HOY_TEST)).toBe(true);
  });

  it('false para un mes anterior, aunque sea el mismo año', () => {
    expect(esMesEnCursoReal({ year: 2026, month: 5 }, HOY_TEST)).toBe(false);
  });

  it('false para el mismo mes de un año distinto', () => {
    expect(esMesEnCursoReal({ year: 2025, month: 6 }, HOY_TEST)).toBe(false);
  });

  it('false para un mes futuro (defensivo, no debería pasar en la práctica)', () => {
    expect(esMesEnCursoReal({ year: 2026, month: 7 }, HOY_TEST)).toBe(false);
  });

  it('undefined (ventana vacía) da false, no rompe', () => {
    expect(esMesEnCursoReal(undefined, HOY_TEST)).toBe(false);
  });
});

// Issue #179: el caso real que motivó el ticket -- confirmado contra
// producción (jobs_historial) que el ETL puede quedarse varias noches sin
// escribir el mes calendario nuevo (el incidente de #111, 23/07→02/08/2026,
// dejó la ventana de planilla_ventas_calculada varada en julio -- ya
// cerrado -- durante los primeros días de agosto). Antes de este fix,
// calcularVta/calcularRotDesEstac asumían POSICIONALMENTE que el último
// elemento del array era "el mes en curso, incompleto" y lo excluían
// siempre -- así que un mes YA CERRADO (el ETL simplemente no llegó a
// escribir el mes nuevo todavía) se perdía en silencio de los totales.
describe('#179: el ETL todavía no escribió el mes en curso -- el último mes de la ventana ya está cerrado', () => {
  // HOY_TEST = 2026-06-15. Si el ETL se atrasó y la ventana todavía termina
  // en mayo (un mes ya cerrado, no "en curso"), ni VTA ni Rot.DesEstac.
  // deben excluirlo -- mismo escenario que dejó el incidente de #111.
  const mesMayoYaCerrado = mes({
    year: 2026, month: 5,
    ventasCantidad: 999,
    estadoMes: 'normal',
    rotacionDiariaDesestacionalizada: 7.0,
  });

  it('calcularVta incluye el último mes si ya está cerrado (no es el mes calendario real)', () => {
    const meses = [mes({ ventasCantidad: 1 }), mesMayoYaCerrado];
    expect(calcularVta(meses, HOY_TEST)).toBe(1000); // 1 + 999, nada excluido
  });

  it('calcularRotDesEstac incluye el último mes si ya está cerrado (no es el mes calendario real)', () => {
    const meses = [
      mes({ estadoMes: 'normal', rotacionDiariaDesestacionalizada: 3.0 }),
      mesMayoYaCerrado,
    ];
    expect(calcularRotDesEstac(meses, HOY_TEST)).toBe(5.0); // (3+7)/2, nada excluido
  });

  it('contraste: el mismo mes SÍ se excluye si de verdad coincide con hoy', () => {
    const mesJunioEnCurso = { ...mesMayoYaCerrado, year: 2026, month: 6 };
    const meses = [mes({ ventasCantidad: 1 }), mesJunioEnCurso];
    expect(calcularVta(meses, HOY_TEST)).toBe(1); // junio sí es HOY_TEST -- se excluye
  });
});

describe('redondearFiabilidad + fiabilidadClass: texto y color coherentes en el borde', () => {
  it('69,5 crudo: texto "70%" y badge verde (69,5 >= 70 solo tras redondear)', async () => {
    const { fiabilidadClass } = await import('../components/PlanillaTable');
    const redondeado = redondearFiabilidad(69.5);
    expect(redondeado).toBe(70);
    expect(`${redondeado}%`).toBe('70%');
    expect(fiabilidadClass(redondeado)).toBe('planilla-badge planilla-badge--verde');
  });

  it('issue #169: caso real C00679 (69,75) -- ANTES del fix el badge era amarillo (69,75 < 70 crudo) pese a mostrar "70%"; DESPUÉS es verde, coherente con el texto', async () => {
    const { fiabilidadClass } = await import('../components/PlanillaTable');
    const crudo = 69.75;

    // Comportamiento viejo (clasificar sobre el crudo, como hacía el bug):
    // documenta la contradicción real que reportó el issue.
    expect(fiabilidadClass(crudo)).toBe('planilla-badge planilla-badge--amarillo');

    // Comportamiento nuevo (clasificar sobre el ya redondeado):
    const redondeado = redondearFiabilidad(crudo);
    expect(redondeado).toBe(70);
    expect(fiabilidadClass(redondeado)).toBe('planilla-badge planilla-badge--verde');
  });

  it('issue #169: caso real T00145E (39,99) -- ANTES del fix el badge era rojo pese a mostrar "40%"; DESPUÉS es amarillo, coherente con la banda 40-69% de la leyenda', async () => {
    const { fiabilidadClass } = await import('../components/PlanillaTable');
    const crudo = 39.99;

    // Comportamiento viejo: 39,99 < 40 crudo -> rojo, pese a que el texto
    // redondeado ya mostraba "40%".
    expect(fiabilidadClass(crudo)).toBe('planilla-badge planilla-badge--rojo');

    // Comportamiento nuevo: 39,99 redondea a 40, que cae en la banda Amarillo.
    const redondeado = redondearFiabilidad(crudo);
    expect(redondeado).toBe(40);
    expect(fiabilidadClass(redondeado)).toBe('planilla-badge planilla-badge--amarillo');
  });
});
