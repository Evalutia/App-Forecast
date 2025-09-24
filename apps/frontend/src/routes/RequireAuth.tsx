import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { getToken, clearAuth, isTokenExpired } from '../features/auth/utils/authStorage';

export default function RequireAuth() {
  const token = getToken();
  const location = useLocation();

  if (!token || isTokenExpired(token)) {
    clearAuth();
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}
