import { useJob } from '../hooks/useJobs';

function formatDateTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const dd = d.toLocaleDateString('es-UY', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const hh = d.toLocaleTimeString('es-UY', { hour: '2-digit', minute: '2-digit' });
  return `${dd} ${hh}`;
}

function estadoBadgeClass(estado: string) {
  if (estado === 'exitoso')   return 'pg-badge pg-badge-green';
  if (estado === 'fallido')   return 'pg-badge pg-badge-red';
  if (estado === 'ejecutando') return 'pg-badge pg-badge-blue';
  if (estado === 'cancelado') return 'pg-badge pg-badge-yellow';
  return 'pg-badge pg-badge-gray';
}

export default function JobDetailPanel({ jobId }: { jobId: number }) {
  const { data: job, isLoading } = useJob(jobId);

  if (isLoading && !job) {
    return (
      <div className="pg-table-card">
        <p className="pg-empty">Cargando…</p>
      </div>
    );
  }
  if (!job) {
    return (
      <div className="pg-table-card">
        <p className="pg-empty">No se encontró el job #{jobId}.</p>
      </div>
    );
  }

  return (
    <div className="pg-table-card" style={{ padding: '24px 28px' }}>

      {/* Header del job */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        paddingBottom: '16px',
        marginBottom: '20px',
      }}>
        <div>
          <h4 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#f0f5f2' }}>
            Job #{job.id}
          </h4>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'rgba(240,245,242,0.45)' }}>
            Tipo: <strong style={{ color: '#34c48f' }}>{job.tipoJob}</strong>
          </p>
        </div>
        <span className={estadoBadgeClass(job.estado)} style={{ fontSize: '12px', padding: '4px 10px' }}>
          {job.estado}
        </span>
      </div>

      {/* Timestamps */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px',
        marginBottom: '20px',
      }}>
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '10px',
          padding: '14px 16px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(240,245,242,0.4)', marginBottom: '6px' }}>
            Inicio
          </div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#f0f5f2' }}>
            {formatDateTime(job.fechaInicio)}
          </div>
        </div>
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: '10px',
          padding: '14px 16px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(240,245,242,0.4)', marginBottom: '6px' }}>
            Fin
          </div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#f0f5f2' }}>
            {formatDateTime(job.fechaFin)}
          </div>
        </div>
      </div>

      {/* Detalle / Warnings */}
      {job.detalle && (
        <div>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(240,245,242,0.4)', marginBottom: '8px' }}>
            Detalle / Warnings
          </div>
          <pre style={{
            whiteSpace: 'pre-wrap',
            background: 'rgba(255,255,255,0.03)',
            padding: '14px 16px',
            borderRadius: '10px',
            border: '1px solid rgba(255,255,255,0.07)',
            color: 'rgba(240,245,242,0.8)',
            fontSize: '13px',
            lineHeight: '1.65',
            margin: 0,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          }}>
            {job.detalle}
          </pre>
        </div>
      )}

    </div>
  );
}
