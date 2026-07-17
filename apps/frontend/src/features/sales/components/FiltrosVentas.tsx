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

  const skuFiltro = useDebouncedValue(sku, 250);
  const { data: skuOptions, isLoading: skusLoading } = useDistinctSkus(skuFiltro, {
    enabled: skuFiltro.trim().length >= 1,
  });
  const skuList = useMemo(() => skuOptions ?? [], [skuOptions]);

  useEffect(() => {
    setFechaDesde(initial?.fechaDesde ?? "");
    setFechaHasta(initial?.fechaHasta ?? "");
    setSku(initial?.sku ?? "");
  }, [initial?.fechaDesde, initial?.fechaHasta, initial?.sku]);

  const handleApply = () => {
    onApply({
      fechaDesde: fechaDesde || undefined,
      fechaHasta: fechaHasta || undefined,
      sku: sku?.trim() || undefined,
      page: 1,
      pageSize: initial?.pageSize ?? 20,
    });
  };

  const handleClear = () => {
    setFechaDesde("");
    setFechaHasta("");
    setSku("");
    onClear?.();
  };

  return (
    <section className="card filters-card ventas-filtros">
      <div className="filters-grid">
        <div className="form-row">
          <label className="label">Desde</label>
          <input
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            className="input"
          />
        </div>

        <div className="form-row">
          <label className="label">Hasta</label>
          <input
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            className="input"
          />
        </div>

        <div className="form-row">
          <label className="label">SKU</label>
          <input
            list="ventas-sku-list"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder={skusLoading ? "Buscando..." : "p.ej. I01497"}
            className="input"
          />
          <datalist id="ventas-sku-list">
            {skuList.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </div>

      </div>

      <div className="filters-actions">
        <button type="button" onClick={handleApply} className="button">Aplicar</button>
        <button type="button" onClick={handleClear} className="button button-ghost">Limpiar</button>
      </div>
    </section>
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
