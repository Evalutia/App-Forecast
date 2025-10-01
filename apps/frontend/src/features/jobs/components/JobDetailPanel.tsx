import { useJob } from '../hooks/useJobs';

function formatDateTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = d.toLocaleDateString(undefined, { day:'2-digit', month:'2-digit', year:'numeric' });
  const hh = d.toLocaleTimeString(undefined, { hour:'2-digit', minute:'2-digit' });
  return `${dd} ${hh}`;
}

export default function JobDetailPanel({ jobId }: { jobId: number }) {
  const { data: job, isLoading } = useJob(jobId);

  if (isLoading && !job) return <section className="card"><div className="muted">Cargando…</div></section>;
  if (!job) return <section className="card"><div className="muted">No se encontró el job.</div></section>;

  return (
    <section className="card" style={{ marginTop: '1rem' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', borderBottom:'1px solid rgba(16,185,129,.14)', paddingBottom:'.75rem' }}>
        <div>
          <h4 style={{ margin:0, fontWeight:800 }}>Job #{job.id}</h4>
          <div className="muted" style={{ marginTop: '.25rem' }}>Tipo: <strong>{job.tipoJob}</strong></div>
        </div>
        <span className="badge badge-default">{job.estado}</span>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'1rem', marginTop:'1rem' }}>
        <div>
          <div className="label" style={{ marginBottom:'.25rem' }}>Inicio</div>
          <div>{formatDateTime(job.fechaInicio)}</div>
        </div>
        <div>
          <div className="label" style={{ marginBottom:'.25rem' }}>Fin</div>
          <div>{formatDateTime(job.fechaFin)}</div>
        </div>
        {job.detalle && (
          <div style={{ gridColumn:'1 / -1' }}>
            <div className="label" style={{ marginBottom:'.25rem' }}>Detalle / Warnings</div>
            <pre style={{ whiteSpace:'pre-wrap', background:'#f7faf9', padding:'0.75rem', borderRadius:'0.75rem', border:'1px solid rgba(16,185,129,.14)' }}>
              {job.detalle}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}
