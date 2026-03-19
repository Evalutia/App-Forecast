import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { clearAuth } from '../utils/authStorage';

export default function LogoutButton() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const handleLogout = () => {
    clearAuth();
    qc.clear();
    navigate('/login', { replace: true });
  };

  return (
    <button onClick={handleLogout} className="btn btn--sm">
      Cerrar sesión
    </button>
  );
}
