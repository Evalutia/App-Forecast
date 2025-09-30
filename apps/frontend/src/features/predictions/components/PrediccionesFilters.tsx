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

export default function PrediccionesFilters({ onChange, className }: Props) {
  const [sp, setSp] = useSearchParams();

  const initial = useMemo(() => ({
    sku: getParam(sp, 'sku') ?? '',
    modelo: getParam(sp, 'modelo') ?? '',
    desde: getParam(sp, 'desde') ?? '',
    hasta: getParam(sp, 'hasta') ?? '',
  }), [sp]);

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
    <div className={['rounded-xl border border-white/10 bg-white/5 p-4', className].filter(Boolean).join(' ')}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-5">
        <div className="sm:col-span-2">
          <label className="block text-sm text-emerald-100/80 mb-1">SKU</label>
          <input
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="p. ej. I01497"
            className="w-full rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-white outline-none"
          />
        </div>

        <div className="sm:col-span-1">
          <label className="block text-sm text-emerald-100/80 mb-1">Modelo</label>
          <input
            value={modelo}
            onChange={(e) => setModelo(e.target.value)}
            placeholder="COMBINADA / RF / XGB…"
            className="w-full rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-white outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-emerald-100/80 mb-1">Desde</label>
          <input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-white outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-emerald-100/80 mb-1">Hasta</label>
          <input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-white outline-none"
          />
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={applyToUrl}
          className="rounded-lg bg-emerald-600/90 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-600"
        >
          Aplicar filtros
        </button>
        <button
          type="button"
          onClick={reset}
          className="rounded-lg border border-white/15 px-3 py-2 text-sm font-medium text-emerald-100/90 hover:bg-white/10"
        >
          Limpiar
        </button>
      </div>
    </div>
  );
}
