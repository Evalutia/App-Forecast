import { useNavigate } from 'react-router-dom';
import { useAuthUser } from '../hooks/useAuthUser';

export default function AdminUsersButton() {
  const { user } = useAuthUser();
  const navigate = useNavigate();

  if (!user || user.role !== 'administrador') return null;

  return (
    <button onClick={() => navigate('/usuarios')} className="btn btn--sm">
      Administrar usuarios
    </button>
  );
}
