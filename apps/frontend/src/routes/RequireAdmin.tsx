import { Navigate, Outlet } from 'react-router-dom';
import { useAuthUser } from '../features/auth/hooks/useAuthUser';

export default function RequireAdmin() {
  const { user, isLoading } = useAuthUser();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== 'administrador') return <Navigate to="/" replace />;
  return <Outlet />;
}
