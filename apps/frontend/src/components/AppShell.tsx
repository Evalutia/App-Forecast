import { AnimatePresence, motion } from 'framer-motion';
import { useLocation, Outlet } from 'react-router-dom';
import { useAuthUser } from '../features/auth/hooks/useAuthUser';
import LogoutButton from '../features/auth/components/LogoutButton';
import '../styles/dark-layout.css';

const DASHBOARD_PATHS = new Set(['/', '/home']);

const variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -8 },
};
const transition = { duration: 0.18, ease: 'easeInOut' as const };

function AppHeader() {
  const { pathname } = useLocation();
  const { user } = useAuthUser();
  const isDashboard = DASHBOARD_PATHS.has(pathname);
  const isAdmin = user?.role === 'administrador';

  return (
    <header className="pg-header">
      <a href="/home" className="pg-brand">Evalutia</a>
      <div className="pg-header-right">
        {isDashboard ? (
          <>
            {user && (
              <span className="pg-role-badge">
                {isAdmin ? 'Administrador' : 'Propietario'}
              </span>
            )}
            {user && <span className="pg-user-email">{user.email}</span>}
            <LogoutButton />
          </>
        ) : (
          <a href="/home" className="pg-back-btn">← Dashboard</a>
        )}
      </div>
    </header>
  );
}

export default function AppShell() {
  const { pathname } = useLocation();

  return (
    <div style={{ minHeight: '100dvh', background: '#050e09', display: 'flex', flexDirection: 'column' }}>
      <AppHeader />
      <AnimatePresence mode="wait">
        <motion.div
          key={pathname}
          variants={variants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={transition}
          style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
