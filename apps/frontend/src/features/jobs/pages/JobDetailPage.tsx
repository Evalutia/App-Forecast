import { Link, useParams } from 'react-router-dom';
import JobDetailPanel from '../../jobs/components/JobDetailPanel';
import '../../../styles/dark-layout.css';

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Detalle de Ejecución</h1>
          <p className="pg-subtitle">Información completa y warnings de la ejecución.</p>
        </div>
      </section>

      <div className="pg-container">
        <div style={{ marginBottom: '4px' }}>
          <Link to="/jobs" className="pg-back-btn" style={{ textDecoration: 'none' }}>
            ← Volver a Ejecuciones
          </Link>
        </div>

        {Number.isNaN(jobId)
          ? (
            <div className="pg-table-card">
              <p className="pg-empty">ID de job inválido.</p>
            </div>
          )
          : <JobDetailPanel jobId={jobId} />
        }
      </div>

    </div>
  );
}
