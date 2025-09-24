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
    <button
      onClick={handleLogout}
      className="rounded-lg bg-emerald-700/70 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
    >
      Cerrar sesión
    </button>
  );
}
