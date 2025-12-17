import type { Prediccion } from '../types/predicciones';

export function getSkuBase(sku: string): string {
  const m = sku.match(/^(.*?)-\d{4}-\d{2}-\d{2}$/);
  return m ? m[1] : sku;
}

export function fmtYearMonth(d: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d.slice(0, 7);
  return d.slice(0, 7); // fallback defensivo
}

export function fmtDateHour(iso: string): string {
  const parts = iso.replace('T', ' ').split(' ');
  if (parts.length < 2) return iso;
  const [date, time] = parts;
  const hour = time.split(':')[0] ?? '00';
  return `${date} ${hour}`;
}

export function horizonLabel(h: number | null | undefined): string {
  if (typeof h === 'number' && h > 0) return `Mes ${h}`;
  return 'h=?';
}

export function ascendingYYYYMM(a: string, b: string) {
  return a.slice(0, 7).localeCompare(b.slice(0, 7));
}

export function groupAvgByModelo(preds: Prediccion[]) {
  const acc: Record<string, { r2Sum: number; r2Cnt: number; rmseSum: number; rmseCnt: number }> = {};
  preds.forEach(p => {
    const key = p.modelo || '—';
    if (!acc[key]) acc[key] = { r2Sum: 0, r2Cnt: 0, rmseSum: 0, rmseCnt: 0 };
    if (typeof p.r2 === 'number') { acc[key].r2Sum += p.r2; acc[key].r2Cnt += 1; }
    if (typeof p.rmse === 'number') { acc[key].rmseSum += p.rmse; acc[key].rmseCnt += 1; }
  });
  return Object.entries(acc).map(([modelo, v]) => ({
    modelo,
    r2Avg: v.r2Cnt ? v.r2Sum / v.r2Cnt : null,
    rmseAvg: v.rmseCnt ? v.rmseSum / v.rmseCnt : null,
  }));
}

export function toYearMonth(d: string): string {
  return d.slice(0, 7); // "YYYY-MM"
}

export function pickMonthlyProjection(
  items: Prediccion[],
  preferModelo: string | null = 'COMBINADA'
) {
  const byYm = new Map<string, Prediccion>();

  const isBetter = (curr: Prediccion | undefined, cand: Prediccion) => {
    if (!curr) return true;
    if (preferModelo && cand.modelo === preferModelo && curr.modelo !== preferModelo) return true;
    if (preferModelo && curr.modelo === preferModelo && cand.modelo !== preferModelo) return false;
    return (cand.tsGeneracion ?? '') > (curr.tsGeneracion ?? '');
  };

  for (const p of items) {
    const ym = toYearMonth(p.fechaPredicha);
    const curr = byYm.get(ym);
    if (isBetter(curr, p)) byYm.set(ym, p);
  }

  const labels = Array.from(byYm.keys()).sort();
  const values = labels.map((ym) => byYm.get(ym)!.cantidadPredicha);
  return { labels, values };
}

export function toQuarterLabelFromDate(d: string): string {
  const dt = new Date(d);
  if (!isNaN(dt.getTime())) {
    const y = dt.getFullYear();
    const q = Math.floor(dt.getMonth() / 3) + 1;
    return `${y}-Q${q}`;
  }
  // fallback: try YYYY-MM
  const m = d.match(/^(\d{4})-(\d{2})/);
  if (m) {
    const y = Number(m[1]);
    const month = Number(m[2]);
    const q = Math.floor((month - 1) / 3) + 1;
    return `${y}-Q${q}`;
  }
  return d;
}


export function quarterRangeFromDate(fechaPredicha: string): { desde: string; hasta: string } {
  // desde = fecha_predicha exacta de esa predicción (SIN MODIFICAR)
  const desde = fechaPredicha; // Mantener el string original
  
  // hasta = fecha_predicha + 3 meses (exactamente 3 meses después para trimestre completo)
  const fecha = new Date(fechaPredicha + 'T00:00:00'); // Asegurar medianoche para evitar problemas de zona horaria
  const hasta = new Date(fecha);
  hasta.setMonth(fecha.getMonth() + 3);
  hasta.setDate(hasta.getDate() - 1); // Último día del trimestre
  
  const formatDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  
  return { 
    desde: desde, // Usar el string original sin modificar
    hasta: formatDate(hasta) 
  };
}

export function pickQuarterlyProjection(items: Prediccion[], preferModelo: string | null = 'COMBINADA') {
  const byQ = new Map<string, Prediccion>();

  const isBetter = (curr: Prediccion | undefined, cand: Prediccion) => {
    if (!curr) return true;
    if (preferModelo && cand.modelo === preferModelo && curr.modelo !== preferModelo) return true;
    if (preferModelo && curr.modelo === preferModelo && cand.modelo !== preferModelo) return false;
    return (cand.tsGeneracion ?? '') > (curr.tsGeneracion ?? '');
  };

  for (const p of items) {
    const qlab = toQuarterLabelFromDate(p.fechaPredicha);
    const curr = byQ.get(qlab);
    if (isBetter(curr, p)) byQ.set(qlab, p);
  }

  const labels = Array.from(byQ.keys()).sort();
  const values = labels.map((lab) => byQ.get(lab)!.cantidadPredicha);
  return { labels, values };
}

// Función para formatear números según las reglas especificadas
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  
  // Si tiene 4+ cifras, mostrar sin comas
  if (Math.abs(value) >= 1000) {
    return Math.floor(value).toString();
  }
  
  // Si tiene menos de 4 cifras, mostrar con una coma si es decimal
  if (value % 1 !== 0) {
    return value.toFixed(1).replace('.', ',');
  }
  
  return value.toString();
}

// Función para redondear hacia arriba y formatear pronósticos
export function formatPronostico(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'DATOS INSUFICIENTES';
  
  // Redondear hacia arriba
  const roundedUp = Math.ceil(value);
  
  // Aplicar el mismo formato de números
  return formatNumber(roundedUp);
}
