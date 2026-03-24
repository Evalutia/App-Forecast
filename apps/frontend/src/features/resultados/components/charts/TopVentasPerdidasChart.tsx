import './ChartSetup';
import { Bar } from 'react-chartjs-2';
import { useTopVentasPerdidas, useStockoutDistribution } from '../../hooks/useResultados';

export default function TopVentasPerdidasChart() {
  const { data, isLoading } = useTopVentasPerdidas(10);
  const { data: stockout } = useStockoutDistribution();

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;

  if (!data || data.length === 0) {
    const criticos = stockout?.items?.filter(i => i.categoria === 'Critico') ?? [];
    return (
      <div className="card" style={{ padding: '1.25rem' }}>
        <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
          Top 10 — Ventas perdidas por quiebre de stock (365d)
        </h3>
        <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
          No se pueden estimar ventas perdidas: los SKUs con quiebre nunca tuvieron stock suficiente para establecer una tasa de ventas base.
        </p>
        {criticos.length > 0 && (
          <>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem',
              padding: '0.45rem 0.75rem', background: '#fef2f2', borderRadius: '0.5rem',
              border: '1px solid #fca5a5',
            }}>
              <span style={{ color: '#dc2626', fontWeight: 800, fontSize: '0.8rem' }}>⚠ {criticos.length} SKUs con quiebre crónico (&gt;30% del tiempo sin stock)</span>
            </div>
            <div style={{ maxHeight: '220px', overflowY: 'auto', border: '1px solid #fca5a530', borderRadius: '0.75rem' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
                <thead>
                  <tr style={{ background: '#fef2f230', position: 'sticky', top: 0 }}>
                    <th style={{ padding: '0.4rem 0.75rem', textAlign: 'left', fontWeight: 800, color: '#dc2626' }}>SKU</th>
                    <th style={{ padding: '0.4rem 0.75rem', textAlign: 'left', fontWeight: 800, color: '#dc2626' }}>Descripción</th>
                    <th style={{ padding: '0.4rem 0.75rem', textAlign: 'right', fontWeight: 800, color: '#dc2626' }}>Stockout</th>
                  </tr>
                </thead>
                <tbody>
                  {criticos.map(i => (
                    <tr key={i.sku} style={{ borderTop: '1px solid #e5e7eb30' }}>
                      <td style={{ padding: '0.35rem 0.75rem', fontWeight: 600 }}>{i.sku}</td>
                      <td style={{ padding: '0.35rem 0.75rem', color: 'var(--muted)' }}>{i.descripcion ?? '—'}</td>
                      <td style={{ padding: '0.35rem 0.75rem', textAlign: 'right', color: '#dc2626', fontWeight: 700 }}>
                        {i.stockoutRate >= 0 ? `${i.stockoutRate}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    );
  }

  const labels = data.map(d => d.sku.length > 12 ? d.sku.slice(0, 12) + '…' : d.sku);
  const chartData = {
    labels,
    datasets: [{
      label: 'Ventas perdidas (unidades)',
      data: data.map(d => d.ventasPerdidas),
      backgroundColor: '#ef4444',
      borderRadius: 4,
    }],
  };

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
        Top 10 — Ventas perdidas por quiebre de stock (365d)
      </h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
        Los SKUs donde más ventas se pierden por falta de stock. Priorizá la reposición de estos productos.
      </p>
      <Bar data={chartData} options={{
        indexAxis: 'y',
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => data[items[0].dataIndex]?.sku ?? '',
              afterTitle: (items) => data[items[0].dataIndex]?.descripcion ?? '',
            },
          },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: '#e5e7eb40' } },
          y: { grid: { display: false } },
        },
      }} />
    </div>
  );
}
