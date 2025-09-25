import { Navigate, Outlet } from 'react-router-dom';
import { useAuthUser } from '../features/auth/hooks/useAuthUser';

export default function RequireAuth() {
  const { user, isLoading } = useAuthUser();
  if (isLoading) return null; 
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
