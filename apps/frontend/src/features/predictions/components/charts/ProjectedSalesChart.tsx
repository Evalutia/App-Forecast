import './ChartSetup';
import { useState } from 'react';
import { Line } from 'react-chartjs-2';
import type { Prediccion } from '../../types/predicciones';
import { getSkuBase, pickQuarterlyProjection, formatNumber } from '../../utils/format';
import { useVentasAgregadas } from '../../../sales/hooks/useVentas';

type Props = { data: Prediccion[]; sku: string };

/** Label del trimestre actual, p.ej. "2026-Q1" */
function currentQuarterLabel(): string {
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  return `${now.getFullYear()}-Q${q}`;
}

export default function ProjectedSalesChart({ data, sku }: Props) {
  const skuBase = getSkuBase(sku);
  const [startFromZero, setStartFromZero] = useState(true);

  const serieSku = data.filter((p) => getSkuBase(p.sku) === skuBase);

  // Predicciones: agrupar por trimestre (ahora incluye rmse)
  const { labels: predQLabels, values: predQValues, rmseValues: predRmse } =
    pickQuarterlyProjection(serieSku, 'COMBINADA');

  // Ventas históricas agregadas trimestralmente
  const now = new Date();
  const cutoff = new Date(now);
  cutoff.setFullYear(now.getFullYear() - 3);
  const cutoff2022Q4 = new Date('2022-10-01');
  const finalCutoff = cutoff > cutoff2022Q4 ? cutoff2022Q4 : cutoff;
  const fmt = (d: Date) => d.toISOString().slice(0, 10);

  const { data: ventasAg } = useVentasAgregadas(
    { sku: skuBase, agregado: 'trimestral', pageSize: 200, fechaDesde: fmt(finalCutoff) },
    { enabled: true }
  );

  const ventasRows = (ventasAg?.items ?? []).map((r: any) => ({
    label: r.periodo as string,
    value: r.totalCantidad as number,
  }));

  // Unión de labels (histórico + predicciones)
  const labelSet = new Set<string>();
  ventasRows.forEach((r) => labelSet.add(r.label));
  predQLabels.forEach((l) => labelSet.add(l));
  const allLabels = Array.from(labelSet);

  allLabels.sort((a, b) => {
    const ma = a.match(/(\d{4})-Q(\d)/);
    const mb = b.match(/(\d{4})-Q(\d)/);
    if (ma && mb) {
      const ya = Number(ma[1]);
      const yb = Number(mb[1]);
      if (ya !== yb) return ya - yb;
      return Number(ma[2]) - Number(mb[2]);
    }
    return a.localeCompare(b);
  });

  // Mapas de valores
  const ventasMap = new Map<string, number>();
  for (const r of ventasRows) {
    ventasMap.set(r.label, (ventasMap.get(r.label) ?? 0) + r.value);
  }
  const predMap = new Map(predQLabels.map((l, i) => [l, predQValues[i]]));
  const rmseMap = new Map(predQLabels.map((l, i) => [l, predRmse[i]]));

  // Arrays alineados a allLabels
  const histData = allLabels.map((lab) => ventasMap.get(lab) ?? null);
  const predData = allLabels.map((lab) => predMap.get(lab) ?? null);

  // ── Conexión visual: agregar último punto histórico al inicio de la predicción ──
  const firstPredIdx = allLabels.findIndex((lab) => predMap.has(lab));
  if (firstPredIdx > 0 && histData[firstPredIdx - 1] != null) {
    predData[firstPredIdx - 1] = histData[firstPredIdx - 1];
  }

  // ── Bandas de confianza (±1.96 × RMSE → ~95%) ──
  const hasRmse = predRmse.some((v) => v !== null && v > 0);
  const upperBand = allLabels.map((lab) => {
    const val = predMap.get(lab);
    const rmse = rmseMap.get(lab);
    if (val == null || rmse == null) return null;
    return val + 1.96 * rmse;
  });
  const lowerBand = allLabels.map((lab) => {
    const val = predMap.get(lab);
    const rmse = rmseMap.get(lab);
    if (val == null || rmse == null) return null;
    return Math.max(0, val - 1.96 * rmse);
  });

  // ── Trimestre actual ──
  const curQ = currentQuarterLabel();
  const curQIdx = allLabels.indexOf(curQ);

  const noVentasHistoricas = ventasRows.length === 0;

  // ── Datasets ──
  const datasets: any[] = [];
  if (!noVentasHistoricas) {
    datasets.push({
      label: `Ventas históricas (Q) ${skuBase}`,
      data: histData,
      borderColor: 'rgba(54,162,235,0.9)',
      backgroundColor: 'rgba(54,162,235,0.2)',
      pointRadius: 3,
    });
  }
  datasets.push({
    label: `Predicción (Q) ${skuBase}`,
    data: predData,
    borderColor: 'rgba(75,192,192,0.9)',
    backgroundColor: 'rgba(75,192,192,0.2)',
    borderDash: [6, 4],
    pointRadius: 3,
  });
  if (hasRmse) {
    datasets.push({
      label: 'Banda superior (95%)',
      data: upperBand,
      borderColor: 'rgba(75,192,192,0.25)',
      backgroundColor: 'transparent',
      borderDash: [2, 2],
      pointRadius: 0,
      fill: false,
    });
    datasets.push({
      label: 'Banda inferior (95%)',
      data: lowerBand,
      borderColor: 'rgba(75,192,192,0.25)',
      backgroundColor: 'rgba(75,192,192,0.08)',
      borderDash: [2, 2],
      pointRadius: 0,
      fill: '-1', // llena entre banda inferior y banda superior
    });
  }

  const ds = { labels: allLabels, datasets };

  // ── Annotation: línea vertical en el trimestre actual ──
  const annotations: Record<string, any> = {};
  if (curQIdx >= 0) {
    annotations.currentQuarter = {
      type: 'line' as const,
      xMin: curQIdx,
      xMax: curQIdx,
      borderColor: 'rgba(255,206,86,0.55)',
      borderWidth: 1.5,
      borderDash: [4, 4],
      label: {
        display: true,
        content: 'Trimestre actual',
        position: 'start' as const,
        backgroundColor: 'rgba(255,206,86,0.25)',
        color: '#111827',
        font: { size: 10 },
        padding: 6,
      },
    };
  }

  return (
    <div className="rounded-xl bg-white/5 p-4">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h4 className="text-base font-semibold text-white" style={{ margin: 0 }}>Ventas proyectadas</h4>
        <label style={{ fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={startFromZero}
            onChange={() => setStartFromZero((v) => !v)}
          />
          Escala desde 0
        </label>
      </div>
      <p className="mb-3 text-xs text-emerald-100/70">
        Serie trimestral: ventas históricas (acotado a 3 años) y predicción.
        {hasRmse && ' La banda sombreada indica el intervalo de confianza al 95%.'}
      </p>
      {noVentasHistoricas && (
        <div className="mb-2 text-sm text-amber-100">
          No se encontraron ventas históricas agregadas para este SKU — mostrando solo predicción.
        </div>
      )}
      <Line
        data={ds}
        options={{
          responsive: true,
          plugins: {
            legend: {
              display: true,
              labels: {
                filter: (item) => {
                  // Ocultar bandas del legend para no saturar
                  if (item.text?.startsWith('Banda')) return false;
                  return true;
                },
              },
            },
            tooltip: {
              callbacks: {
                label(ctx) {
                  const dsLabel = ctx.dataset.label ?? '';
                  const val = ctx.parsed.y;
                  if (dsLabel.startsWith('Banda')) return null as any;
                  const prefix = dsLabel.includes('Predicción') ? 'Predicción' : 'Ventas';
                  return `${prefix}: ${formatNumber(val)} unidades`;
                },
              },
            },
            annotation: { annotations },
          },
          scales: {
            x: { ticks: { autoSkip: true, maxTicksLimit: 12 } },
            y: { beginAtZero: startFromZero },
          },
          elements: { point: { radius: 2 } },
        }}
      />
    </div>
  );
}
