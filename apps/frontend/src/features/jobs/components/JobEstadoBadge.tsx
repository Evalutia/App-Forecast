import type { JobItem } from '../types/jobs';

type Props = { estado: JobItem['estado']; className?: string };

const MAP: Record<string, string> = {
  pendiente: 'bg-gray-100 text-gray-800 ring-1 ring-gray-200',
  ejecutando: 'bg-blue-100 text-blue-800 ring-1 ring-blue-200',
  exitoso: 'bg-green-100 text-green-800 ring-1 ring-green-200',
  fallido: 'bg-red-100 text-red-800 ring-1 ring-red-200',
  cancelado: 'bg-yellow-100 text-yellow-800 ring-1 ring-yellow-200',
};

export default function JobEstadoBadge({ estado, className = '' }: Props) {
  const k = (estado || 'desconocido').toLowerCase();
  const cls = MAP[k] ?? 'bg-slate-100 text-slate-800 ring-1 ring-slate-200';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${cls} ${className}`}>
      {estado || 'desconocido'}
    </span>
  );
}
