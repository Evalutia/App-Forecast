import './ChartSetup';
import { Line } from 'react-chartjs-2';
import type { Prediccion } from '../../types/predicciones';
import { fmtYearMonth, ascendingYYYYMM, getSkuBase } from '../../utils/format';

type Props = {
  data: Prediccion[];
  sku: string;
};

export default function ProjectedSalesChart({ data, sku }: Props) {
  const skuBase = getSkuBase(sku);
  const serie = data
    .filter(p => getSkuBase(p.sku) === skuBase)
    .sort((a, b) => ascendingYYYYMM(a.fechaPredicha, b.fechaPredicha));

  const labels = serie.map(p => fmtYearMonth(p.fechaPredicha));
  const values = serie.map(p => p.cantidadPredicha);

  const ds = {
    labels,
    datasets: [
      {
        label: `Proyección ${skuBase}`,
        data: values,
      },
    ],
  };

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h4 className="text-base font-semibold text-white">Ventas proyectadas</h4>
      <p className="mb-3 text-xs text-emerald-100/70">
        Serie mensual predicha para el SKU seleccionado (solo predicciones).
      </p>
      <Line data={ds} options={{
        responsive: true,
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: true } },
      }} />
    </div>
  );
}
