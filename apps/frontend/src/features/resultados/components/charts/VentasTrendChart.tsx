import './ChartSetup';
import { Line } from 'react-chartjs-2';
import { useVentasTrend } from '../../hooks/useResultados';

export default function VentasTrendChart() {
  const { data, isLoading } = useVentasTrend(24);

  if (isLoading) return <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>Cargando...</div>;
  if (!data || data.length === 0) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
        Sin datos de ventas mensuales.
      </div>
    );
  }

  const chartData = {
    labels: data.map(d => d.periodo),
    datasets: [
      {
        label: 'Unidades vendidas',
        data: data.map(d => d.totalUnidades),
        borderColor: '#059669',
        backgroundColor: '#05966920',
        fill: true,
        tension: 0.3,
        yAxisID: 'y',
      },
      {
        label: 'SKUs activos',
        data: data.map(d => d.skusActivos),
        borderColor: '#0ea5e9',
        backgroundColor: 'transparent',
        borderDash: [5, 3],
        tension: 0.3,
        yAxisID: 'y1',
      },
    ],
  };

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <h3 style={{ fontSize: '0.85rem', fontWeight: 800, marginBottom: '0.5rem', color: 'var(--emerald-950)' }}>
        Tendencia de ventas mensuales (últimos 24 meses)
      </h3>
      <p style={{ fontSize: '0.72rem', color: 'var(--muted)', marginBottom: '0.75rem' }}>
        Evolución de unidades vendidas y cantidad de SKUs activos mes a mes. Permite detectar estacionalidad y tendencias.
      </p>
      <Line data={chartData} options={{
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { padding: 12, font: { size: 11 } },
          },
        },
        scales: {
          y: {
            type: 'linear',
            position: 'left',
            beginAtZero: true,
            title: { display: true, text: 'Unidades', font: { size: 11 } },
            grid: { color: '#e5e7eb40' },
          },
          y1: {
            type: 'linear',
            position: 'right',
            beginAtZero: true,
            title: { display: true, text: 'SKUs activos', font: { size: 11 } },
            grid: { display: false },
          },
          x: {
            grid: { color: '#e5e7eb20' },
            ticks: { maxRotation: 45 },
          },
        },
      }} />
    </div>
  );
}
