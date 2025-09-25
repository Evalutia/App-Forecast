import { useNavigate } from 'react-router-dom';
import { useAuthUser } from '../hooks/useAuthUser';

export default function AdminUsersButton() {
  const { user } = useAuthUser();
  const navigate = useNavigate();

  if (!user || user.role !== 'administrador') return null;

  return (
    <button
      onClick={() => navigate('/usuarios')}
      className="rounded-lg bg-emerald-700/80 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
    >
      Administrar usuarios
    </button>
  );
}
