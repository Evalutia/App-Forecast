// apps/frontend/src/apps/predicciones/pages/PrediccionesPage.tsx
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import PrediccionesFilters from '../components/PrediccionesFilters';
import PrediccionesTable from '../components/PrediccionesTable';
import DatosExtra from '../components/DatosExtra';
import TopSkusVentasTable from '../components/TopSkusVentasTable';

export default function PrediccionesPage() {
  return (
    <div className="predicciones-page">
      {/* ===== Header (clon 1:1 de Ventas) ===== */}
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>

        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      {/* ===== Contenido ===== */}
      <div className="predicciones-container">
        <header className="section-head">
          <h1 className="section-title">Predicciones</h1>
          <p className="section-subtitle">
            Consultá el top de SKUs, explorá el resumen por producto y revisá el historial de predicciones.
          </p>
        </header>

        <h2 className="subsection-title">Top 20 productos más vendidos (últimos 12 meses)</h2>
        <TopSkusVentasTable />
        
        <div className="section-divider"></div>

        <h2 className="subsection-title">Resumen y proyección por SKU</h2>
        <DatosExtra />
        
        <div className="section-divider"></div>

        <h2 className="subsection-title">Historial de predicciones</h2>
        <PrediccionesFilters />
        <PrediccionesTable />
      </div>
    </div>
  );
}
