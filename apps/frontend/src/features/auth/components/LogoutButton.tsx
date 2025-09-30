import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

export default function LogoutButton() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const handleLogout = () => {
    localStorage.removeItem('auth.token');
    localStorage.removeItem('auth.user');
    qc.clear();
    navigate('/login', { replace: true });
  };

  return (
    <button onClick={handleLogout} className="btn btn--sm">
      Cerrar sesión
    </button>
  );
}
