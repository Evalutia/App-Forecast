import './ChartSetup';
import { Bar } from 'react-chartjs-2';
import { useTopVentasPerdidas } from '../../hooks/useResultados';

export default function TopVentasPerdidasChart() {
  const { data, isLoading } = useTopVentasPerdidas(10);

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;
  if (!data || data.length === 0) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
        Sin datos suficientes para calcular ventas perdidas (se requieren ≥ 30 días de stock).
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
