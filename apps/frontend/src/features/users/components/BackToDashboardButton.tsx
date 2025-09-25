import { useNavigate } from 'react-router-dom';

export default function BackToDashboardButton() {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate('/')}
      className="rounded-lg bg-white/10 px-3 py-1.5 text-sm font-medium text-white hover:bg-white/20"
    >
      ← Volver al dashboard
    </button>
  );
}
