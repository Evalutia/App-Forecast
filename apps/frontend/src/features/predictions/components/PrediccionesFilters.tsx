import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

type Props = {
  onChange?: (filtros: {
    sku?: string;
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
    }),
    [sp]
  );

  const [sku, setSku] = useState(initial.sku);

  useEffect(() => {
    const t = setTimeout(() => {
      onChange?.({
        sku: sku || undefined,
      });
    }, 200);
    return () => clearTimeout(t);
  }, [sku, onChange]);

  const applyToUrl = useCallback(() => {
    const next = new URLSearchParams(sp);
    const setOrDel = (k: string, v?: string) => {
      if (v && v.length) next.set(k, v);
      else next.delete(k);
    };
    setOrDel('sku', sku);
    next.delete('desde');
    next.delete('hasta');
    next.set('page', '1');
    setSp(next, { replace: true });
  }, [sp, setSp, sku]);

  const reset = useCallback(() => {
    setSku('');
    const next = new URLSearchParams(sp);
    ['sku', 'desde', 'hasta', 'page'].forEach((k) => next.delete(k));
    next.set('page', '1');
    setSp(next, { replace: true });
  }, [sp, setSp]);

  return (
    <section className="card filters-card predicciones-filtros">
      {/* === grilla centrada (un solo filtro) === */}
      <div className="filters-grid filters-grid--single">
        <div className="form-row">
          <label className="label">SKU</label>
          <input
            className="input"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="p.ej. I01497"
          />
        </div>
      </div>

      {/* === acciones abajo === */}
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
