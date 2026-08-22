import { describe, expect, it } from 'vitest';
import type { PlanillaSugerenciaDto } from '../types/planilla';
import { estadoMesBg, fiabilidadClass, resolveAeCell } from './PlanillaTable';

// Estas pruebas cubren las funciones puras que `PlanillaTable.tsx` exporta a
// propósito (mismo patrón que `fiabilidadClass` ya usaba) para poder probar
// color/lógica de celda sin montar el componente completo -- no hay setup de
// React Testing Library en este archivo, ni hace falta.

describe('estadoMesBg', () => {
  it('sin_datos pinta un tono discreto, distinto de vacío y de sin_stock (#177)', () => {
    const color = estadoMesBg('sin_datos');
    expect(color).not.toBe('');
    expect(color).not.toBe(estadoMesBg('sin_stock'));
  });

  it('estado desconocido no pinta nada (comportamiento previo intacto)', () => {
    expect(estadoMesBg('normal')).toBe('');
  });

  it('sin_stock sigue pintando gris (regresión)', () => {
    expect(estadoMesBg('sin_stock')).toBe('rgba(100,116,139,0.18)');
  });

  it('quiebre_parcial con ingresoDuranteQuiebre sigue ganando sobre frecuencia (regresión #145)', () => {
    expect(estadoMesBg('quiebre_parcial', 'baja', true)).toBe('rgba(41,182,246,0.24)');
  });
});

describe('resolveAeCell (#178)', () => {
  function sug(overrides: Partial<PlanillaSugerenciaDto>): PlanillaSugerenciaDto {
    return {
      sku: 'X',
      rotacionSugerida: null,
      fiabilidadPorcentaje: null,
      diasHastaQuiebre: null,
      ...overrides,
    };
  }

  it('sin sugerencia (undefined) no hay nada que mostrar', () => {
    expect(resolveAeCell(undefined)).toBeNull();
  });

  it('rotacionSugerida y fiabilidad ambos null no hay nada que mostrar', () => {
    expect(resolveAeCell(sug({}))).toBeNull();
  });

  it('caso normal: rotacion y fiabilidad presentes, ambos se muestran', () => {
    const data = resolveAeCell(sug({ rotacionSugerida: 2.3456, fiabilidadPorcentaje: 82.4 }));
    expect(data).not.toBeNull();
    expect(data!.rotacionLabel).toBe('2.3456');
    expect(data!.fiabilidad).toEqual({ pct: 82, className: fiabilidadClass(82) });
  });

  it('rotacionSugerida null pero fiabilidad presente: el badge se muestra igual (bug de #178)', () => {
    const data = resolveAeCell(sug({ rotacionSugerida: null, fiabilidadPorcentaje: 55 }));
    expect(data).not.toBeNull();
    expect(data!.rotacionLabel).toBeNull();
    expect(data!.fiabilidad).toEqual({ pct: 55, className: fiabilidadClass(55) });
  });

  it('rotacionSugerida presente pero fiabilidad null: se muestra sólo la rotación', () => {
    const data = resolveAeCell(sug({ rotacionSugerida: 1.5, fiabilidadPorcentaje: null }));
    expect(data).not.toBeNull();
    expect(data!.rotacionLabel).toBe('1.5000');
    expect(data!.fiabilidad).toBeNull();
  });
});
