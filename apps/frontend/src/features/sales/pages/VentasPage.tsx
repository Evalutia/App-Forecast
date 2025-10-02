import { useState } from "react";
import type { VentasQuery } from "../../sales/types/ventas";
import FiltrosVentas from "../../sales/components/FiltrosVentas";
import TablaVentas from "../../sales/components/TablaVentas";
import BackToDashboardButton from "../../users/components/BackToDashboardButton";

export default function VentasPage() {
  const [query, setQuery] = useState<VentasQuery>({ page: 1, pageSize: 50 });

  const handleApply = (q: VentasQuery) => setQuery(q);
  const handleClear = () => setQuery({ page: 1, pageSize: 50 });
  const handlePageChange = (page: number) => setQuery((prev) => ({ ...prev, page }));

  return (
    <div className="ventas-page">
      <div className="ventas-header">
        <a href="/home" className="ventas-brand">Evalutia</a>

        <div className="ventas-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="ventas-container">
        <header className="section-head">
          <h1 className="section-title">Ventas</h1>
          <p className="section-subtitle">Explorá el historial de ventas en detalle.</p>
        </header>

        <FiltrosVentas initial={query} onApply={handleApply} onClear={handleClear} />

        <div style={{ marginTop: "1rem", width: "100%" }}>
          <TablaVentas query={query} onPageChange={handlePageChange} />
        </div>
      </div>
    </div>
  );
}
