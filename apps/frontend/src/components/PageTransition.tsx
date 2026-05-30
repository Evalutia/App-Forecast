import { AnimatePresence, motion } from 'framer-motion';
import { useLocation, Outlet } from 'react-router-dom';

const variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0  },
  exit:    { opacity: 0, y: -8 },
};

const transition = { duration: 0.18, ease: 'easeInOut' as const };

export default function PageTransition() {
  const { pathname } = useLocation();

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pathname}
        variants={variants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={transition}
      >
        <Outlet />
      </motion.div>
    </AnimatePresence>
  );
}
