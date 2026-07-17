import type { SkuStockAnalysis } from '../types/resultados';
import Modal from '../../users/components/shared/Modal';

type Props = {
  item: SkuStockAnalysis;
  onClose: () => void;
};

function fmt(n: number | null | undefined): string {
  if (n == null) return 'N/A';
  return n.toLocaleString('es-AR');
}

function stockoutBadge(rate: number) {
  const color = rate > 30 ? '#dc2626' : rate > 15 ? '#d97706' : '#16a34a';
  const bg = rate > 30 ? '#fef2f2' : rate > 15 ? '#fffbeb' : '#f0fdf4';
  const label = rate > 30 ? 'CRÍTICO' : rate > 15 ? 'MODERADO' : 'BUENO';
  return (
    <span style={{
      display: 'inline-block',
      padding: '0.15rem 0.5rem',
      borderRadius: '0.375rem',
      fontSize: '0.7rem',
      fontWeight: 800,
      letterSpacing: '0.05em',
      color,
      background: bg,
      border: `1px solid ${color}20`,
    }}>
      {label} — {rate}%
    </span>
  );
}

export default function SkuDetailModal({ item, onClose }: Props) {
  return (
    <Modal title={`Análisis — ${item.sku}`} onClose={onClose} maxWidth="44rem">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem 1.5rem' }}>
        {[
          ['Descripción', item.descripcion ?? '—'],
          ['Stock mínimo', fmt(item.stockMinimo)],
          ['Ventas (365 días)', fmt(item.ventas365)],
          ['Días con stock (365d)', fmt(item.diasConStock365)],
          ['Días sin stock (365d)', fmt(item.diasSinStock365)],
          ['Ventas / día con stock', item.ventasPorDiaConStock365 != null ? item.ventasPorDiaConStock365.toLocaleString('es-AR') : 'N/A'],
          ['Tasa de stockout', null],
          ['Ventas perdidas estimadas', fmt(item.ventasPerdidasEstimadas365)],
          ['Pronóstico próx. trimestre', fmt(item.pronosticoProximoTrimestre)],
          ['Sugerencia compra (90 días)', fmt(item.sugerenciaCompra90)],
        ].map(([label, value]) => (
          <div key={label as string}>
            <div style={{
              fontSize: '0.72rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--muted)',
              marginBottom: '0.2rem',
            }}>
              {label}
            </div>
            <div style={{ fontSize: '0.95rem', color: 'var(--emerald-950)', wordBreak: 'break-word' }}>
              {label === 'Tasa de stockout' ? stockoutBadge(item.stockoutRate365) : String(value)}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
