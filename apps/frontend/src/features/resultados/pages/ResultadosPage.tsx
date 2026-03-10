import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';

export default function ResultadosPage() {
  return (
    <div className="predicciones-page">
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>
        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="predicciones-container">
        <header className="section-head">
          <h1 className="section-title">Resultados</h1>
          <p className="section-subtitle">Próximamente disponible.</p>
        </header>
      </div>

      <ScrollToTopButton />
    </div>
  );
}
