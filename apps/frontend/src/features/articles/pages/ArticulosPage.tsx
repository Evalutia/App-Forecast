import { useEffect, useMemo, useState } from 'react';
import api from '../../../api/client';

export default function ArticulosPage() {
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(100);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    api.get('/api/Articulos', { params: { pagina: page, tamanioPagina: pageSize } })
      .then(res => {
        if (cancelled) return;
        const data = res.data;
        // soportar respuesta PagedResultDto o array
        if (Array.isArray(data)) {
          setItems(data);
          setTotal(data.length);
        } else {
          setItems(data.items ?? data.Items ?? []);
          setTotal(data.total ?? data.Total ?? 0);
        }
      })
      .catch(() => {
        if (!cancelled) { setItems([]); setTotal(0); }
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });

    return () => { cancelled = true; };
  }, [page, pageSize]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil((total || 0) / pageSize)), [total, pageSize]);

  return (
    <>
      <div className="articulos-topbar-wide">
        <div className="home-header">
          <a href="/home" className="home-brand">EVALUTIA</a>
          <div className="home-actions">
            <a href="/home" className="btn btn--sm">← Volver al dashboard</a>
          </div>
        </div>
      </div>

      <div className="articulos-page">
        <div className="articulos-container">
        <header className="section-head">
          <h1 className="section-title">Artículos</h1>
          <p className="section-subtitle">Listado de artículos cargados en la base de datos.</p>
        </header>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Descripción</th>
                <th>Familia</th>
                <th>Género</th>
                <th>Sección</th>
                <th>Marca</th>
                <th>Temporada</th>
                <th>fact_desc_min</th>
                <th>fact_desc_max</th>
                <th>desc_valida</th>
                <th>stock_minimo</th>
                <th>actualizado_en</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 12 }).map((__, j) => (
                      <td key={j}><span className="skeleton skel-20" /></td>
                    ))}
                  </tr>
                ))
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={12} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                    No hay resultados.
                  </td>
                </tr>
              ) : (
                items.map((a: any) => (
                  <tr key={a.sku ?? a.Sku}>
                    <td className="mono">{a.sku ?? a.Sku}</td>
                    <td>{a.descripcion ?? a.Descripcion}</td>
                    <td>{a.familia_nombre ?? a.FamiliaNombre}</td>
                    <td>{a.genero_descripcion ?? a.GeneroDescripcion}</td>
                    <td>{a.seccion_nombre ?? a.SeccionNombre ?? a.seccion_nombre}</td>
                    <td>{a.marca_nombre ?? a.MarcaNombre ?? a.marca_nombre}</td>
                    <td>{a.temporada_nombre ?? a.TemporadaNombre ?? a.temporada_nombre}</td>
                    <td>{a.fact_desc_min ?? a.FactDescMin}</td>
                    <td>{a.fact_desc_max ?? a.FactDescMax}</td>
                    <td>{a.desc_valida ?? a.DescValida ? 'Sí' : 'No'}</td>
                    <td>{a.stock_minimo ?? a.StockMinimo}</td>
                    <td className="muted">{a.actualizado_en ?? a.ActualizadoEn ?? '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="pager" style={{ marginTop: '0.6rem' }}>
          <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
          <div className="pager-buttons">
            <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</button>
            <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</button>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
