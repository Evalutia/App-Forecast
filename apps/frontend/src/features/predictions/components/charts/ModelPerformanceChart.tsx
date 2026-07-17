import './ChartSetup';
import { Bar } from 'react-chartjs-2';
import type { Prediccion } from '../../types/predicciones';
import { groupAvgByModelo } from '../../utils/format';

type Props = { data: Prediccion[] };

export default function ModelPerformanceChart({ data }: Props) {
  // Promedio por modelo
  const rows = groupAvgByModelo(data).sort((a, b) => (b.r2Avg ?? -1) - (a.r2Avg ?? -1));
  const labels = rows.map(r => r.modelo);
  const r2 = rows.map(r => r.r2Avg ?? 0);

  const ds = {
    labels,
    datasets: [
      {
        label: 'R² promedio',
        data: r2,
      },
    ],
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="mb-3 text-xs text-emerald-100/70">
        Promedio de R² según las predicciones listadas. (Cuanto más alto, mejor).
      </p>
      <Bar data={ds} options={{
        responsive: true,
        plugins: { legend: { display: true } },
        scales: {
          y: { beginAtZero: true, max: 1 },
        },
      }} />
    </div>
  );
}
