import React from 'react';
import { Link } from 'react-router-dom';

type Props = { jobId: number; children?: React.ReactNode };

export default function JobPrediccionesLink({ jobId, children }: Props) {
  const to = `/predicciones?jobId=${encodeURIComponent(jobId)}`;
  return (
    <Link
      to={to}
      className="text-blue-600 hover:text-blue-700 hover:underline font-medium"
    >
      {children ?? 'Ver predicciones'}
    </Link>
  );
}
