import { useEffect, useMemo, useState } from "react";
import type { VentasQuery } from "../types/ventas";
import { useDistinctSkus } from "../hooks/useVentas";

type Props = {
  initial?: VentasQuery;
  onApply: (q: VentasQuery) => void;
  onClear?: () => void;
};

export default function FiltrosVentas({ initial, onApply, onClear }: Props) {
  const [fechaDesde, setFechaDesde] = useState(initial?.fechaDesde ?? "");
  const [fechaHasta, setFechaHasta] = useState(initial?.fechaHasta ?? "");
  const [sku, setSku] = useState(initial?.sku ?? "");
  const [pageSize, setPageSize] = useState<number>(initial?.pageSize ?? 50);

  const skuFiltro = useDebouncedValue(sku, 250);
  const { data: skuOptions, isLoading: skusLoading } = useDistinctSkus(skuFiltro, {
    enabled: skuFiltro.trim().length >= 1,
  });
  const skuList = useMemo(() => skuOptions ?? [], [skuOptions]);

  useEffect(() => {
    setFechaDesde(initial?.fechaDesde ?? "");
    setFechaHasta(initial?.fechaHasta ?? "");
    setSku(initial?.sku ?? "");
    setPageSize(initial?.pageSize ?? 50);
  }, [initial?.fechaDesde, initial?.fechaHasta, initial?.sku, initial?.pageSize]);

  const handleApply = () => {
    onApply({
      fechaDesde: fechaDesde || undefined,
      fechaHasta: fechaHasta || undefined,
      sku: sku?.trim() || undefined,
      page: 1,
      pageSize,
    });
  };

  const handleClear = () => {
    setFechaDesde("");
    setFechaHasta("");
    setSku("");
    setPageSize(50);
    onClear?.();
  };

  return (
    <div className="w-full rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="flex flex-col">
          <label className="text-sm font-medium text-gray-700">Desde</label>
          <input
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring"
          />
        </div>

        <div className="flex flex-col">
          <label className="text-sm font-medium text-gray-700">Hasta</label>
          <input
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring"
          />
        </div>

        <div className="flex flex-col lg:col-span-2">
          <label className="text-sm font-medium text-gray-700">SKU</label>
          <input
            list="ventas-sku-list"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder={skusLoading ? "Buscando..." : "Escribí para sugerencias"}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring"
          />
          <datalist id="ventas-sku-list">
            {skuList.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>

        <div className="flex flex-col">
          <label className="text-sm font-medium text-gray-700">Filas por página</label>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="mt-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring"
          >
            {[25, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={handleApply}
          className="rounded-xl bg-gray-900 px-4 py-2 text-sm font-semibold text-white shadow hover:opacity-90"
        >
          Aplicar
        </button>
        <button
          type="button"
          onClick={handleClear}
          className="rounded-xl border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          Limpiar
        </button>
      </div>
    </div>
  );
}

function useDebouncedValue<T>(value: T, delay = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}
