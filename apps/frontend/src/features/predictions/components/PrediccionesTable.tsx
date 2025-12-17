import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { usePrediccionesSearch } from '../hooks/usePredicciones';
import type { PrediccionSearchParams } from '../types/predicciones';
import { exportAllPredicciones } from '../utils/exportPredicciones';
import { quarterRangeFromDate, formatPronostico } from '../utils/format';

type Props = { className?: string };

function getParam(sp: URLSearchParams, k: string) {
  const v = sp.get(k);
  return v && v.length ? v : undefined;
}
function getInt(sp: URLSearchParams, k: string, def: number) {
  const v = Number(sp.get(k));
  return Number.isFinite(v) && v > 0 ? v : def;
}

export default function PrediccionesTable({ className }: Props) {
  const [sp, setSp] = useSearchParams();

  const [exporting, setExporting] = useState(false);

  const params: PrediccionSearchParams = useMemo(() => ({
    sku: getParam(sp, 'sku'),
    desde: getParam(sp, 'desde'),
    hasta: getParam(sp, 'hasta'),
    page: getInt(sp, 'page', 1),
    pageSize: getInt(sp, 'pageSize', 20),
  }), [sp]);

  const { data, isLoading, isFetching, isError, error } = usePrediccionesSearch(params);
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 20;
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const setPage = (nextPage: number) => {
    const next = new URLSearchParams(sp);
    next.set('page', String(nextPage));
    setSp(next, { replace: true });
  };

  const setPageSize = (nextPageSize: number) => {
    const next = new URLSearchParams(sp);
    next.set('pageSize', String(nextPageSize));
    next.set('page', '1'); // reset a la primera página
    setSp(next, { replace: true });
  };

  if (isError) {
    return <div className="alert">Ocurrió un error al cargar el historial. {(error as any)?.message ?? ''}</div>;
  }

  const handleExport = async () => {
    try {
      setExporting(true);
      await exportAllPredicciones(params);
    } catch (err) {
      console.error('Error exportando predicciones', err);
      throw err;
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className={['card table-card', className].filter(Boolean).join(' ')}>
      <div style={{ marginBottom: '.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="muted">{isFetching ? 'Actualizando…' : ''}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          <div className="muted"></div>
        </div>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th className="sku-column">SKU</th>
              <th>Fecha predicha desde</th>
              <th>Fecha predicha hasta</th>
              <th>R²</th>
              <th>RMSE</th>
              <th className="cantidad-column">Cantidad predicha</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td><span className="skeleton skel-28" /></td>
                  <td><span className="skeleton skel-20" /></td>
                  <td><span className="skeleton skel-20" /></td>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-12" /></td>
                </tr>
              ))
            ) : isError ? (
              <tr>
                <td colSpan={6} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                  No se pudieron cargar las predicciones.
                </td>
              </tr>
            ) : (data?.items?.length ?? 0) === 0 ? (
              <tr>
                <td colSpan={6} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                  No se encontraron predicciones.
                </td>
              </tr>
            ) : (
              data?.items?.map((prediccion) => {
                const { desde, hasta } = quarterRangeFromDate(prediccion.fechaPredicha);
                return (
                  <tr key={prediccion.id}>
                    <td className="sku-column">{prediccion.sku}</td>
                    <td>{desde}</td>
                    <td>{hasta}</td>
                    <td>{prediccion.r2 ? prediccion.r2.toFixed(3) : '—'}</td>
                    <td>{prediccion.rmse ? prediccion.rmse.toFixed(2) : '—'}</td>
                    <td className="cantidad-column">{formatPronostico(prediccion.cantidadPredicha)}</td>
                  </tr>
                );
              }) ?? []
            )}
          </tbody>
        </table>
      </div>

      {/* Fila separadora para el botón Descargar Excel */}
      <div className="export-row">
        <button
          className="pager-btn export-btn"
          disabled={exporting || isFetching || isLoading}
          onClick={handleExport}
          title="Descargar todas las predicciones en Excel"
          type="button"
        >
          {exporting ? 'Exportando…' : 'Descargar Excel'}
        </button>
      </div>

      {/* Paginador */}
      <div className="pager">
        <div>Página {page} de {totalPages}</div>
        <div className="pager-buttons">
          <button
            className="pager-btn"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Anterior
          </button>
          <button
            className="pager-btn"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>

      {/* Selector de tamaño (mostrado como en las otras secciones) */}
      <div style={{ marginTop: '.5rem' }} className="muted">
        Filas por página:&nbsp;
        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
          {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>
    </section>
  );
}
