import { describe, expect, it } from 'vitest';
import type { Cell } from 'exceljs';
import { buildPlanillaWorkbook, CRITERIOS_COLUMNAS } from './exportPlanilla';
import type { PlanillaMesDto, PlanillaSugerenciaDto, PlanillaVentasDto } from '../types/planilla';

// Fixture mínima: ventana normalizada de 3 meses (may/jun/jul 2026, jul = mes
// de referencia), un SKU con historia completa y otro recién dado de alta con
// placeholder sin_datos (#106).

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

const skuA: PlanillaVentasDto = {
  sku: 'SKU-A',
  descripcion: 'ARTICULO COMPLETO',
  codigoBarras: '779123',
  marcaNombre: null,
  generoDescripcion: 'NOTEBOOKS',
  stockMinimo: 1,
  estadoArticulo: 'activo',
  meses: [
    mes({ month: 5, ventasCantidad: 100, ticketsMes: 5, valorHistorico: 80, valorAjustado: 90, criterioFrecuencia: 'historico', rotacionDiariaDesestacionalizada: 3.1 }),
    mes({ month: 6, ventasCantidad: 50, estadoMes: 'quiebre_parcial', frecuenciaNivel: 'media', rotacionDiariaReal: 2, rotacionAjustada: 2.2, valorAjustado: 60, criterioFrecuencia: 'promedio' }),
    mes({ month: 7, ventasCantidad: 10, valorAjustado: 10, criterioFrecuencia: 'real_extrapolado' }),
  ],
};

const skuB: PlanillaVentasDto = {
  sku: 'SKU-B',
  descripcion: 'ALTA NUEVA',
  codigoBarras: null,
  marcaNombre: null,
  generoDescripcion: null,
  stockMinimo: null,
  estadoArticulo: 'discontinuo',
  meses: [
    // Placeholder sin_datos (#106): valores null, no ceros.
    mes({ month: 5, estadoMes: 'sin_datos', ventasCantidad: null, diasConStock: null, ticketsMes: null }),
    mes({ month: 6, ventasCantidad: 7, ticketsMes: 2 }),
    // Issue #122: rotacionDiariaReal viene en 0 (no null) del backend para
    // meses sin_stock -- el fixture antes tenía null por default, que no
    // reproducía el bug real (el `?? 0`/`!= null` de exportPlanilla.ts solo
    // fallaba con 0 explícito, no con null).
    mes({ month: 7, estadoMes: 'sin_stock', ventasCantidad: 0, diasConStock: 0, rotacionDiariaReal: 0 }),
  ],
};

const sugerencias = new Map<string, PlanillaSugerenciaDto>([
  ['SKU-A', { sku: 'SKU-A', rotacionSugerida: 1.5, fiabilidadPorcentaje: 80, diasHastaQuiebre: 12.3 }],
]);

function fillColor(cell: Cell): string | undefined {
  const fill = cell.fill;
  return fill && fill.type === 'pattern' ? fill.fgColor?.argb : undefined;
}

function headerValues(values: Cell['value'][] | { [key: string]: Cell['value'] }): Cell['value'][] {
  return (values as Cell['value'][]).slice(1); // exceljs: row.values es 1-based
}

describe('buildPlanillaWorkbook (#107)', () => {
  const wb = buildPlanillaWorkbook([skuA, skuB], sugerencias);
  const hoja1 = wb.getWorksheet('Planilla de Reposición')!;
  const hoja2 = wb.getWorksheet('Detalle de cálculo')!;

  it('crea exactamente las tres hojas, en orden', () => {
    expect(wb.worksheets.map(w => w.name)).toEqual(['Planilla de Reposición', 'Detalle de cálculo', 'Criterios']);
  });

  it('hoja 1: headers idénticos al layout original del cliente + agregados a la derecha', () => {
    expect(headerValues(hoja1.getRow(1).values)).toEqual([
      'Articulo', 'Descripcion', 'Codigos Barras',
      'Vta.May/26', 'Vta.Jun/26', 'Vta.Jul/26',
      'May/26', 'Jun/26', 'Jul/26',
      'Rotacion DesEstac.', 'Estado Art.', 'VTA', 'DDSTK',
      'ROT.S', 'Fiabilidad %', 'QBK (días)', 'Género',
    ]);
  });

  it('hoja 1: no incluye las columnas descartadas en #33', () => {
    const headers = headerValues(hoja1.getRow(1).values).map(String);
    for (const prohibida of ['SIN STOCK', 'TOT STK', 'C/STK', 'Rot. Manual']) {
      expect(headers).not.toContain(prohibida);
    }
  });

  it('hoja 1: Estado Art. sale como texto y QBK redondeado', () => {
    const filaA = hoja1.getRow(2); // SKU-A
    expect(filaA.getCell(11).value).toBe('activo');
    expect(filaA.getCell(16).value).toBe(12); // QBK 12.3 → 12
    expect(filaA.getCell(17).value).toBe('NOTEBOOKS'); // Género al final
  });

  it('hoja 1: mes sin_datos exporta celda vacía con fondo gris claro, no un 0', () => {
    const filaB = hoja1.getRow(3); // SKU-B
    expect(filaB.getCell(4).value).toBeNull();       // Vta.May/26
    expect(fillColor(filaB.getCell(4))).toBe('FFF1F5F9');
    expect(filaB.getCell(7).value).toBeNull();       // Rot May/26
  });

  it('hoja 1: mes sin_stock exporta rotación vacía, no 0,0000 (#122)', () => {
    // SKU-B, Jul/26 (índice 2, el último mes): sin_stock con
    // rotacionDiariaReal=0 -- la hoja Criterios promete "Vacía si el mes no
    // tuvo ningún día con stock" para esta columna.
    const filaB = hoja1.getRow(3);
    expect(filaB.getCell(9).value).toBeNull(); // Rot.Jul/26
  });

  it('hoja 1: color de quiebre en la celda mensual (media freq → naranja)', () => {
    const filaA = hoja1.getRow(2);
    expect(fillColor(filaA.getCell(5))).toBe('FFFFB74D'); // Vta.Jun/26 quiebre media
  });

  it('hoja 1: VTA suma solo meses cerrados y trata sin_datos como 0', () => {
    expect(hoja1.getRow(2).getCell(12).value).toBe(150); // SKU-A: 100+50
    expect(hoja1.getRow(3).getCell(12).value).toBe(7);   // SKU-B: null→0 + 7
  });

  it('hoja 1: Rotacion DesEstac. excluye el mes quiebre_parcial sin factor estacional (#117)', () => {
    // SKU-A: May/26 normal con factor (desest=3.1), Jun/26 quiebre_parcial
    // SIN factor (rotacionDiariaDesestacionalizada=null por default del
    // fixture, solo tiene rotacionAjustada=2.2). Antes del fix, Jun caía a
    // un fallback que empujaba 2.2 sin corregir -> promedio (3.1+2.2)/2=2.65,
    // mezclando un valor crudo en una columna "corregida por estacionalidad".
    // Con el fix, Jun se excluye por no tener factor -> promedio = 3.1 (May solo).
    expect(hoja1.getRow(2).getCell(10).value).toBe(3.1);
  });

  it('hoja 2: anclas + 5 bloques mensuales del blending', () => {
    expect(headerValues(hoja2.getRow(3).values)).toEqual([
      'Articulo', 'Descripcion',
      'Tick.May/26', 'Tick.Jun/26', 'Tick.Jul/26',
      'Hist.May/26', 'Hist.Jun/26', 'Hist.Jul/26',
      'V/E.May/26', 'V/E.Jun/26', 'V/E.Jul/26',
      'Crit.May/26', 'Crit.Jun/26', 'Crit.Jul/26',
      'VAj.May/26', 'VAj.Jun/26', 'VAj.Jul/26',
    ]);
  });

  it('hoja 2: leyenda de criterios en la fila 1 con los colores de la paleta #65', () => {
    expect(hoja2.getCell(1, 1).value).toBe('Método del valor ajustado (VAj):');
    expect(hoja2.getCell(1, 3).value).toBe('Histórico');
    expect(fillColor(hoja2.getCell(1, 3))).toBe('FFBFDBFE');  // azul
    expect(hoja2.getCell(1, 6).value).toBe('Promedio');
    expect(fillColor(hoja2.getCell(1, 6))).toBe('FFDDD6FE');  // violeta
    expect(hoja2.getCell(1, 9).value).toBe('Venta real / Extrapolado');
    expect(fillColor(hoja2.getCell(1, 9))).toBe('FF99F6E4');  // teal
  });

  it('hoja 2: VAj con fondo por criterio y etiqueta legible en Crit', () => {
    const filaA = hoja2.getRow(4); // SKU-A
    expect(fillColor(filaA.getCell(15))).toBe('FFBFDBFE'); // VAj.May historico → azul
    expect(fillColor(filaA.getCell(16))).toBe('FFDDD6FE'); // VAj.Jun promedio → violeta
    expect(fillColor(filaA.getCell(17))).toBe('FF99F6E4'); // VAj.Jul real_extrapolado → teal
    expect(filaA.getCell(12).value).toBe('Histórico');
    expect(filaA.getCell(13).value).toBe('Promedio');
    expect(filaA.getCell(14).value).toBe('Venta real');    // normal → Venta real
  });

  it('hoja 2: mes sin_datos queda vacío también en el detalle', () => {
    const filaB = hoja2.getRow(5); // SKU-B
    expect(filaB.getCell(3).value).toBeNull();  // Tick.May
    expect(filaB.getCell(12).value).toBe('');   // Crit.May sin etiqueta
    expect(filaB.getCell(15).value).toBeNull(); // VAj.May
    expect(fillColor(filaB.getCell(15))).toBe('FFF1F5F9'); // gris sin_datos, no color de criterio
  });

  it('hoja 2: mes sin_stock exporta V/E vacío, no 0,00 (#122)', () => {
    // Mismo bug que en hoja 1: rotacionDiariaReal=0 (no null) para
    // sin_stock hacía que `!= null` calculara 0*dias=0 en vez de dejar
    // la celda vacía como promete "Criterios" para esta columna.
    const filaB = hoja2.getRow(5); // SKU-B
    expect(filaB.getCell(11).value).toBeNull(); // V/E.Jul (índice 2, sin_stock)
  });
});

describe('hoja Criterios (#109)', () => {
  const wb = buildPlanillaWorkbook([skuA, skuB], sugerencias);
  const hoja1 = wb.getWorksheet('Planilla de Reposición')!;
  const hoja2 = wb.getWorksheet('Detalle de cálculo')!;
  const criterios = wb.getWorksheet('Criterios')!;

  // Header real 'Vta.May/26' → fila genérica 'Vta.[mes]', 'May/26' → '[mes]'
  const MES_RE = /^([A-Z][a-zá-ú]{2}\/\d{2})$/i;
  function normalizar(header: string): string {
    if (MES_RE.test(header)) return '[mes]';
    return header.replace(/[A-Z][a-zá-ú]{2}\/\d{2}$/i, '[mes]');
  }

  const filasCriterios = new Set(CRITERIOS_COLUMNAS.map(c => c.col));
  const textoCompleto = criterios.getSheetValues().flat().map(String).join('\n');

  it('toda columna de la hoja 1 tiene su fila en Criterios', () => {
    for (const h of headerValues(hoja1.getRow(1).values).map(String)) {
      expect(filasCriterios, `header sin explicar: ${h}`).toContain(normalizar(h));
    }
  });

  it('toda columna de la hoja 2 tiene su fila en Criterios', () => {
    for (const h of headerValues(hoja2.getRow(3).values).map(String)) {
      expect(filasCriterios, `header sin explicar: ${h}`).toContain(normalizar(h));
    }
  });

  it('las 5 columnas que el cliente preguntó están explicadas', () => {
    for (const col of ['QBK (días)', 'ROT.S', 'Fiabilidad %', 'DDSTK', 'Estado Art.']) {
      expect(filasCriterios).toContain(col);
    }
  });

  it('incluye las bandas de tickets y la leyenda de colores con swatches pintados', () => {
    expect(textoCompleto).toContain('2 tickets o menos');
    expect(textoCompleto).toContain('5 tickets o más');
    // swatch de quiebre alta frecuencia pintado en la sección de colores
    let amarillo = false;
    criterios.eachRow(row => {
      const c = row.getCell(1);
      if (c.value === 'Amarillo' && fillColor(c) === 'FFFFCA28') amarillo = true;
    });
    expect(amarillo).toBe(true);
  });

  it('lenguaje para el cliente: sin jerga interna ni nombres de tablas/enums', () => {
    for (const jerga of ['planilla_ventas_calculada', 'ventas_historicas', 'stock_diario',
                         'estado_mes', 'real_extrapolado', 'quiebre_parcial', 'NULL', 'null',
                         'frecuencia_nivel', 'valor_ajustado', 'API', 'backend']) {
      expect(textoCompleto, `jerga encontrada: ${jerga}`).not.toContain(jerga);
    }
  });
});
