import { Navigate } from 'react-router-dom';
import { useAuthUser } from '../features/auth/hooks/useAuthUser';
import AppShell from '../components/AppShell';

export default function RequireAuth() {
  const { user, isLoading } = useAuthUser();

  if (isLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
      </div>
    );
  }

  return user ? <AppShell /> : <Navigate to="/login" replace />;
}
