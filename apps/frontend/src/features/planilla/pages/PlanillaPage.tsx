import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';

export default function PlanillaPage() {
  return (
    <div className="planilla-page">
      <div className="planilla-header">
        <a href="/home" className="planilla-brand">Evalutia</a>
        <div className="planilla-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="planilla-container">
        <header className="section-head">
          <h1 className="section-title">Planilla de Reposición</h1>
          <p className="section-subtitle">
            Rotación histórica y métricas de reposición por artículo.
          </p>
        </header>

        {/* Filtros — issue #13 */}
        <section className="card filters-card planilla-filtros">
          <div className="planilla-filtros-placeholder">
            <span className="skeleton skel-120" />
            <span className="skeleton skel-120" />
          </div>
        </section>

        {/* Tabla — issue #11 */}
        <section className="card table-card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Descripción</th>
                  <th>Marca</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    <td><span className="skeleton skel-60" /></td>
                    <td><span className="skeleton skel-180" /></td>
                    <td><span className="skeleton skel-80" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <ScrollToTopButton />
    </div>
  );
}
