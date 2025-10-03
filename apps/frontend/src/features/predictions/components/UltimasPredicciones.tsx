import { Link, useSearchParams } from 'react-router-dom';
import { useUltimasPredicciones } from '../hooks/usePredicciones';

export default function UltimasPredicciones() {
  const { data, isLoading, isError /*, refetch*/ } = useUltimasPredicciones();
  const [, setSp] = useSearchParams();

  const goToHistorialConSku = (sku: string) => {
    const next = new URLSearchParams();
    next.set('sku', sku);
    next.set('page', '1');
    setSp(next);
  };

  // ====== Estados compactos y sin "tarjeta blanca" ======
  if (isLoading) {
    return (
      <div className="status-banner status--loading">
        <span className="status-icon"><span className="spinner" /></span>
        <span className="status-text">Cargando últimas predicciones…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="status-banner status--error">
        <span className="status-icon" aria-hidden>⚠️</span>
        <span className="status-text">No se pudieron cargar las últimas predicciones.</span>
        {/* <button className="status-action" onClick={() => refetch()}>Reintentar</button> */}
      </div>
    );
  }

  const items = data ?? [];

  // Si no hay datos, no mostramos nada (evitamos huecos visuales)
  if (items.length === 0) return null;

  // ====== Lista normal (misma estética que el resto) ======
  return (
    <div className="predicciones-ultimas card">
      <div className="mb-3" style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <h3 style={{margin:0,color:'#064e3b'}}>Últimas predicciones</h3>
        <span className="muted" style={{fontSize:'.8rem'}}>{items.length} ítems</span>
      </div>

      <ul style={{listStyle:'none',margin:0,padding:0}}>
        {items.map((p) => (
          <li
            key={p.id ?? `${p.sku}-${p.fechaPredicha}-${p.modelo}-${p.horizonte}-${p.versionModelo ?? ''}-${p.tsGeneracion ?? ''}`}
            style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'.6rem 0',borderTop:'1px solid rgba(16,185,129,.14)'}}
          >
            <div style={{minWidth:0}}>
              <div style={{display:'flex',alignItems:'center',gap:'.5rem'}}>
                <span style={{display:'inline-flex',alignItems:'center',borderRadius:'6px',background:'#f7faf9',padding:'.1rem .4rem',fontSize:'.75rem',color:'#065f46'}}>
                  {p.sku}
                </span>
                <span style={{fontSize:'.95rem',color:'#0f172a'}}>
                  {' - ' + p.fechaPredicha} → <span style={{fontWeight:700}}>{p.cantidadPredicha}</span>
                </span>
              </div>
              <div className="muted" style={{fontSize:'.8rem',marginTop:'.15rem'}}>
                {p.modelo} {p.versionModelo} · h={p.horizonte} · gen: {p.tsGeneracion}
              </div>
            </div>

            <div style={{display:'flex',alignItems:'center',gap:'.6rem',flexShrink:0}}>
              {typeof p.jobId === 'number' && (
                <Link to={`/predicciones?jobId=${p.jobId}&page=1`} title="Ver predicciones de este job">
                  Job #{p.jobId}
                </Link>
              )}
              <button
                type="button"
                onClick={() => goToHistorialConSku(p.sku)}
                className="button button-ghost"
              >
                Ver historial del SKU
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
