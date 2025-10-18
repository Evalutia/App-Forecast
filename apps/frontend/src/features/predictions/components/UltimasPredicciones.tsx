// apps/frontend/src/apps/predicciones/components/UltimasPredicciones.tsx
import { Link, useSearchParams } from 'react-router-dom';
import { useUltimasPredicciones } from '../hooks/usePredicciones';

function getInt(sp: URLSearchParams, k: string, def: number) {
  const v = Number(sp.get(k));
  return Number.isFinite(v) && v > 0 ? v : def;
}

export default function UltimasPredicciones() {
  const { data, isLoading, isError /*, refetch*/ } = useUltimasPredicciones();
  const [sp, setSp] = useSearchParams();

  // --- estado de paginado (solo cliente) ----
  const page = getInt(sp, 'ultPage', 1);
  const pageSize = getInt(sp, 'ultPageSize', 10);

  const setPage = (nextPage: number) => {
    const next = new URLSearchParams(sp);
    next.set('ultPage', String(nextPage));
    setSp(next, { replace: true });
  };

  const setPageSize = (nextPageSize: number) => {
    const next = new URLSearchParams(sp);
    next.set('ultPageSize', String(nextPageSize));
    next.set('ultPage', '1'); // reset
    setSp(next, { replace: true });
  };

  const goToHistorialConSku = (sku: string) => {
    const next = new URLSearchParams(sp);
    // Filtros del historial
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
  if (items.length === 0) return null;

  // ---- paginado cliente ----
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = (page - 1) * pageSize;
  const end = Math.min(start + pageSize, total);
  const pageItems = items.slice(start, end);

  return (
    <div className="predicciones-ultimas card">
      <div className="mb-3" style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <h3 style={{margin:0,color:'#064e3b'}}>Últimas predicciones</h3>
        <span className="muted" style={{fontSize:'.8rem'}}>{total} ítems</span>
      </div>

      <ul style={{listStyle:'none',margin:0,padding:0}}>
        {pageItems.map((p) => (
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

      {/* Paginador igual al de Ventas/Historial */}
      <div className="pager">
        <div>
          Página {page} de {totalPages}
          <span className="muted"> &nbsp;·&nbsp; Mostrando {start + 1}–{end}</span>
        </div>
        <div className="pager-buttons">
          <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
          <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</button>
        </div>
      </div>

      {/* selector de tamaño (opcional) */}
      <div style={{ marginTop: '.5rem' }} className="muted">
        Filas por página:&nbsp;
        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
          {[5,10,20,50].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>
    </div>
  );
}
