import { Link } from 'react-router-dom';

type Props = {
  jobId?: number | null;
  className?: string;
};

export default function PrediccionesByJobLink({ jobId, className }: Props) {
  if (typeof jobId !== 'number') {
    return <span className={className ?? ''}>—</span>;
  }
  return (
    <Link
      to={`/predicciones?jobId=${jobId}&page=1`}
      className={['text-emerald-200 hover:underline', className].filter(Boolean).join(' ')}
      title="Ver predicciones de este job"
    >
      #{jobId}
    </Link>
  );
}
