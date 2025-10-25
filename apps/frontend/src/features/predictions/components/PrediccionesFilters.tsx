import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

type Props = {
  onChange?: (filtros: {
    sku?: string;
    modelo?: string;
    desde?: string;
    hasta?: string;
  }) => void;
  className?: string;
};

function getParam(sp: URLSearchParams, key: string) {
  const v = sp.get(key);
  return v && v.length ? v : undefined;
}

export default function PrediccionesFilters({ onChange }: Props) {
  const [sp, setSp] = useSearchParams();

  const initial = useMemo(
    () => ({
      sku: getParam(sp, 'sku') ?? '',
      modelo: getParam(sp, 'modelo') ?? '',
      desde: getParam(sp, 'desde') ?? '',
      hasta: getParam(sp, 'hasta') ?? '',
    }),
    [sp]
  );

  const [sku, setSku] = useState(initial.sku);
  const [modelo, setModelo] = useState(initial.modelo);
  const [desde, setDesde] = useState(initial.desde);
  const [hasta, setHasta] = useState(initial.hasta);

  useEffect(() => {
    const t = setTimeout(() => {
      onChange?.({
        sku: sku || undefined,
        modelo: modelo || undefined,
        desde: desde || undefined,
        hasta: hasta || undefined,
      });
    }, 200);
    return () => clearTimeout(t);
  }, [sku, modelo, desde, hasta, onChange]);

  const applyToUrl = useCallback(() => {
    const next = new URLSearchParams(sp);
    const setOrDel = (k: string, v?: string) => {
      if (v && v.length) next.set(k, v);
      else next.delete(k);
    };
    setOrDel('sku', sku);
    setOrDel('modelo', modelo);
    setOrDel('desde', desde);
    setOrDel('hasta', hasta);
    next.set('page', '1');
    setSp(next, { replace: true });
  }, [sp, setSp, sku, modelo, desde, hasta]);

  const reset = useCallback(() => {
    setSku('');
    setModelo('');
    setDesde('');
    setHasta('');
    const next = new URLSearchParams(sp);
    ['sku', 'modelo', 'desde', 'hasta', 'page'].forEach((k) => next.delete(k));
    next.set('page', '1');
    setSp(next, { replace: true });
  }, [sp, setSp]);

  return (
    <section className="card filters-card predicciones-filtros">
      {/* === grilla idéntica a Jobs === */}
      <div className="filters-grid">
        <div className="form-row">
          <label className="label">SKU</label>
          <input
            className="input"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="p.ej. I01497"
          />
        </div>

        <div className="form-row">
          <label className="label">Modelo</label>
          <input
            className="input"
            value={modelo}
            onChange={(e) => setModelo(e.target.value)}
            placeholder="RF / XGB"
          />
        </div>

        <div className="form-row">
          <label className="label">Desde</label>
          <input
            type="date"
            className="input"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
          />
        </div>

        <div className="form-row">
          <label className="label">Hasta</label>
          <input
            type="date"
            className="input"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
          />
        </div>
      </div>

      {/* === acciones abajo, exacto a Jobs === */}
      <div className="filters-actions">
        <button type="button" className="button" onClick={applyToUrl}>
          Aplicar filtros
        </button>
        <button type="button" className="button button-ghost" onClick={reset}>
          Limpiar
        </button>
      </div>
    </section>
  );
}
