import { useTopSkusVentas } from '../hooks/usePredicciones';
import { formatNumber, formatPronostico } from '../utils/format';

type Props = {
  className?: string;
  take?: number;
};

export default function TopSkusVentasTable({ className, take = 20 }: Props) {
  const { data, isLoading, isError } = useTopSkusVentas(take);

  return (
    <section className={['card table-card', className].filter(Boolean).join(' ')}>
      <div style={{ marginBottom: '.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th className="ranking-column">Ranking</th>
              <th className="sku-column">SKU</th>
              <th>Ventas totales (12m)</th>
              <th>% Ventas totales</th>
              <th className="pronostico-column">Pronóstico próximo trimestre</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  <td><span className="skeleton skel-8" /></td>
                  <td><span className="skeleton skel-28" /></td>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-12" /></td>
                  <td><span className="skeleton skel-12" /></td>
                </tr>
              ))
            ) : isError ? (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                  No se pudo cargar el Top de SKUs.
                </td>
              </tr>
            ) : (data?.length ?? 0) === 0 ? (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                  Sin ventas en los últimos 12 meses.
                </td>
              </tr>
            ) : (
              <>
                {(data ?? []).filter(r => r.sku !== 'TOTAL').map((r, index) => (
                  <tr key={r.sku}>
                    <td className="ranking-column">{index + 1}</td>
                    <td className="mono sku-column">{r.sku}</td>
                    <td>{formatNumber(r.ventasTotales)}</td>
                    <td>{r.porcentajeVentas ? `${r.porcentajeVentas.toFixed(2)}%` : '—'}</td>
                    <td className="pronostico-column">{formatPronostico(r.pronosticoProximoTrimestre)}</td>
                  </tr>
                ))}
                {(data ?? []).find(r => r.sku === 'TOTAL') && (
                  <tr className="total-row">
                    <td colSpan={5} className="total-cell">
                      <div className="total-content">
                        <span className="total-label">Cantidad total de unidades vendidas los últimos 12 meses:</span>
                        <span className="total-number">{formatNumber((data ?? []).find(r => r.sku === 'TOTAL')?.ventasTotales || 0)}</span>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
