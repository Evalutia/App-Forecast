import { useMemo, useState } from 'react';
import { useStockAnalysis } from '../hooks/useResultados';
import type { SkuStockAnalysis, StockAnalysisParams } from '../types/resultados';
import SkuDetailModal from './SkuDetailModal';
import StockFilters from './StockFilters';
import { exportAllResultados } from '../utils/exportResultados';

function fmt(n: number | null | undefined): string {
  if (n == null) return 'N/A';
  return n.toLocaleString('es-AR');
}

function stockoutCell(rate: number) {
  const color = rate > 30 ? '#dc2626' : rate > 15 ? '#d97706' : '#16a34a';
  return <span style={{ color, fontWeight: 700 }}>{rate}%</span>;
}

export default function StockAnalysisTable() {
  const [skuInput, setSkuInput] = useState('');
  const [sku, setSku] = useState('');
  const [orderBy, setOrderBy] = useState('');
  const [orderByInput, setOrderByInput] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState<SkuStockAnalysis | null>(null);
  const [exporting, setExporting] = useState(false);

  const params: StockAnalysisParams = useMemo(() => ({
    sku: sku || undefined,
    orderBy: orderBy || undefined,
    page,
    pageSize,
  }), [sku, orderBy, page, pageSize]);

  const { data, isLoading, isError } = useStockAnalysis(params);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const handleSearch = () => {
    setSku(skuInput);
    setOrderBy(orderByInput);
    setPage(1);
  };

  const handleReset = () => {
    setSkuInput('');
    setSku('');
    setOrderByInput('');
    setOrderBy('');
    setPage(1);
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      await exportAllResultados(params);
    } catch (err) {
      console.error('Error exportando resultados', err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <StockFilters
        sku={skuInput}
        onSkuChange={setSkuInput}
        orderBy={orderByInput}
        onOrderByChange={setOrderByInput}
        onSearch={handleSearch}
        onReset={handleReset}
      />

      <section className="card table-card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Descripción</th>
                <th>Ventas 365d</th>
                <th>Días c/Stock</th>
                <th>Días s/Stock</th>
                <th>Stockout</th>
                <th>Ventas perdidas est.</th>
                <th>Sugerencia 90d</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 8 }).map((_, j) => (
                      <td key={j}><span className="skeleton skel-20" /></td>
                    ))}
                  </tr>
                ))
              ) : isError ? (
                <tr>
                  <td colSpan={8} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                    No se pudieron cargar los datos.
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                    No hay resultados.
                  </td>
                </tr>
              ) : (
                items.map(r => (
                  <tr key={r.sku} style={{ cursor: 'pointer' }} onClick={() => setSelected(r)}>
                    <td className="mono" style={{ color: 'var(--emerald-700)', fontWeight: 700 }}>{r.sku}</td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.descripcion ?? '—'}
                    </td>
                    <td>{fmt(r.ventas365)}</td>
                    <td>{fmt(r.diasConStock365)}</td>
                    <td>{fmt(r.diasSinStock365)}</td>
                    <td>{stockoutCell(r.stockoutRate365)}</td>
                    <td style={{ color: (r.ventasPerdidasEstimadas365 ?? 0) > 0 ? '#dc2626' : undefined }}>
                      {fmt(r.ventasPerdidasEstimadas365)}
                    </td>
                    <td style={{ fontWeight: 700 }}>{fmt(r.sugerenciaCompra90)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="export-row">
          <button
            className="pager-btn export-btn"
            disabled={exporting || isLoading}
            onClick={handleExport}
            title="Descargar todos los resultados en Excel"
            type="button"
          >
            {exporting ? 'Exportando…' : 'Descargar Excel'}
          </button>
        </div>

        <div className="pager">
          <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
          <div className="pager-buttons">
            <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</button>
            <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
          </div>
        </div>
        <div style={{ marginTop: '.5rem' }} className="muted">
          Filas por página:&nbsp;
          <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </section>

      {selected && <SkuDetailModal item={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
