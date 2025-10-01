import { Link, useParams } from 'react-router-dom';
import JobDetailPanel from '../../jobs/components/JobDetailPanel';

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);

  return (
    <div className="jobs-page">
      <div className="jobs-container">
        <header className="section-head" style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <div>
            <h1 className="section-title">Detalle del Job</h1>
            <p className="section-subtitle">Información y warnings de la ejecución.</p>
          </div>
          <Link to="/jobs" className="button button-ghost">← Volver</Link>
        </header>

        {Number.isNaN(jobId)
          ? <section className="card"><div className="muted">ID inválido.</div></section>
          : <JobDetailPanel jobId={jobId} />
        }
      </div>
    </div>
  );
}
