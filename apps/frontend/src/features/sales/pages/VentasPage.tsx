// src/features/ventas/pages/VentasPage.tsx
import { useState, useMemo } from "react";
import type { VentasQuery } from "../../sales/types/ventas";
import FiltrosVentas from "../../sales/components/FiltrosVentas";
import TablaVentas from "../../sales/components/TablaVentas";
import TablaVentasAgregadas from "../../sales/components/TablaVentasAgregadas";

export default function VentasPage() {
  const [query, setQuery] = useState<VentasQuery>({
    page: 1,
    pageSize: 50,
  });

  const isAgregado = useMemo(() => Boolean(query.agregado?.trim()), [query.agregado]);

  const handleApply = (q: VentasQuery) => setQuery(q);
  const handleClear = () =>
    setQuery({
      page: 1,
      pageSize: 50,
    });
  const handlePageChange = (page: number) => setQuery((prev) => ({ ...prev, page }));

  return (
    <div className="mx-auto max-w-7xl p-4">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Ventas</h1>
        <p className="text-sm text-gray-600">
          Explorá el historial de ventas en detalle o de forma agregada por período.
        </p>
      </div>

      <FiltrosVentas initial={query} onApply={handleApply} onClear={handleClear} showAgregado />

      <div className="mt-4">
        {isAgregado ? (
          <TablaVentasAgregadas
            query={query as VentasQuery & { agregado: string }}
            onPageChange={handlePageChange}
          />
        ) : (
          <TablaVentas query={query} onPageChange={handlePageChange} />
        )}
      </div>
    </div>
  );
}
