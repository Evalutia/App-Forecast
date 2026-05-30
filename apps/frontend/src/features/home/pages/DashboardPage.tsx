import { type ReactElement, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuthUser } from '../../auth/hooks/useAuthUser';
import { searchJobs } from '../../jobs/utils/api';
import '../../../styles/home.css';

// ── SVG icons ────────────────────────────────────────────────────────────────

const Icon = ({ d, d2 }: { d: string; d2?: string }) => (
  <svg viewBox="0 0 24 24">
    <path d={d} />
    {d2 && <path d={d2} />}
  </svg>
);

const ICONS: Record<string, ReactElement> = {
  planilla: <Icon d="M3 10h18M3 14h18M10 3v18M14 3v18M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />,
  predicciones: <Icon d="M22 12h-4l-3 9L9 3l-3 9H2" />,
  resultados: <Icon d="M18 20V10M12 20V4M6 20v-6" />,
  'ventas-mensuales': <Icon d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />,
  stock: <Icon d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />,
  articulos: <Icon d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />,
  ventas: <Icon d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />,
  jobs: <Icon d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" d2="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />,
  usuarios: <Icon d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0" />,
};

// ── Module definitions ────────────────────────────────────────────────────────

interface Module {
  href: string;
  title: string;
  desc: string;
  icon: string;
  adminOnly: boolean;
}

const MODULES: Module[] = [
  { href: '/planilla',        title: 'Planilla de Reposición', desc: 'Rotación diaria y estado de stock por SKU en los últimos 13 meses.',    icon: 'planilla',        adminOnly: false },
  { href: '/predicciones',    title: 'Predicciones',           desc: 'Proyecciones de demanda por producto con modelos de machine learning.', icon: 'predicciones',    adminOnly: false },
  { href: '/resultados',      title: 'Resultados',             desc: 'Análisis ABC, tasa de stockout y ventas perdidas estimadas.',           icon: 'resultados',      adminOnly: false },
  { href: '/ventas-mensuales',title: 'Ventas Mensuales',       desc: 'Agregado mensual de unidades vendidas por SKU.',                        icon: 'ventas-mensuales',adminOnly: false },
  { href: '/stock-diario',    title: 'Stock Diario',           desc: 'Inventario diario por producto y depósito.',                           icon: 'stock',           adminOnly: false },
  { href: '/articulos',       title: 'Artículos',              desc: 'Catálogo completo de productos del sistema.',                           icon: 'articulos',       adminOnly: false },
  { href: '/ventas',          title: 'Ventas',                 desc: 'Historial detallado de ventas históricas.',                             icon: 'ventas',          adminOnly: true  },
  { href: '/jobs',            title: 'Ejecuciones',            desc: 'Historial de jobs ETL y corridas de predicción.',                      icon: 'jobs',            adminOnly: true  },
  { href: '/usuarios',        title: 'Usuarios',               desc: 'Gestión de accesos y roles de la plataforma.',                         icon: 'usuarios',        adminOnly: true  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function tiempoDesde(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)   return 'ahora mismo';
  if (mins < 60)  return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)   return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days}d`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { user } = useAuthUser();
  const isAdmin = user?.role === 'administrador';

  // último job ETL exitoso
  const { data: jobData, isLoading: jobLoading } = useQuery({
    queryKey: ['dashboard', 'last-etl'],
    queryFn:  () => searchJobs({ pageSize: 1, tipo: 'etl', estado: 'exitoso' }),
    staleTime: 5 * 60_000,
  });

  // último job ETL (cualquier estado) para detectar fallo
  const { data: jobAnyData } = useQuery({
    queryKey: ['dashboard', 'last-etl-any'],
    queryFn:  () => searchJobs({ pageSize: 1, tipo: 'etl' }),
    staleTime: 5 * 60_000,
  });

  const lastOk   = jobData?.items?.[0];
  const lastAny  = jobAnyData?.items?.[0];
  const etlFallo = lastAny && lastAny.estado === 'fallido';

  // nombre del usuario
  const rawName    = user?.email?.split('@')[0] ?? '';
  const displayName = rawName.charAt(0).toUpperCase() + rawName.slice(1);

  // módulos visibles según rol
  const visibleModules = MODULES.filter(m => !m.adminOnly || isAdmin);

  // scroll-reveal con IntersectionObserver
  const cardRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  useEffect(() => {
    const els = cardRefs.current.filter(Boolean) as HTMLAnchorElement[];
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach(e => {
          if (e.isIntersecting) {
            (e.target as HTMLElement).classList.add('visible');
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, [visibleModules.length]);

  return (
    <div className="home-page">

      {/* ── Hero ── */}
      <section className="home-hero">
        <div className="home-hero-grid" />
        <div className="home-hero-glow" />
        <div className="home-hero-content">
          <div className="home-hero-badge">Panel de gestión</div>
          <h1 className="home-title">
            {displayName ? `Bienvenido, ${displayName}.` : 'Bienvenido.'}
          </h1>
          <p className="home-subtitle">
            Visualizá métricas clave, consultá predicciones y optimizá el inventario de tu empresa desde un solo lugar.
          </p>
        </div>
      </section>

      {/* ── Stats bar ── */}
      <div className="home-stats">
        {/* Estado ETL */}
        <div className="home-stat-item">
          {jobLoading ? (
            <span className="home-stat-dot home-stat-dot--loading" />
          ) : etlFallo ? (
            <span className="home-stat-dot home-stat-dot--err" />
          ) : (
            <span className="home-stat-dot home-stat-dot--ok" />
          )}
          <span>
            {jobLoading
              ? 'Verificando datos…'
              : etlFallo
              ? `ETL con error · ${lastAny?.fechaInicio ? tiempoDesde(lastAny.fechaInicio) : ''}`
              : lastOk
              ? `Datos actualizados · ${tiempoDesde(lastOk.fechaFin ?? lastOk.fechaInicio)}`
              : 'Sin datos de ETL aún'}
          </span>
        </div>

        <span className="home-stat-sep" />

        {/* Módulos disponibles */}
        <div className="home-stat-item">
          <span className="home-stat-dot home-stat-dot--ok" />
          <span>{visibleModules.length} módulos disponibles</span>
        </div>

        {isAdmin && (
          <>
            <span className="home-stat-sep" />
            <div className="home-stat-item">
              <span className="home-stat-dot home-stat-dot--ok" />
              <span>Acceso completo</span>
            </div>
          </>
        )}
      </div>

      {/* ── Module grid ── */}
      <main className="home-modules">
        <p className="home-modules-label">Accesos rápidos</p>

        <div className="home-modules-grid">
          {visibleModules.map((mod, i) => (
            <a
              key={mod.href}
              href={mod.href}
              className={`home-module-card${mod.adminOnly ? ' admin-only' : ''}`}
              ref={el => { cardRefs.current[i] = el; }}
              style={{ animationDelay: `${i * 55}ms` }}
            >
              <div className="home-module-icon">
                {ICONS[mod.icon]}
              </div>
              <div>
                <div className="home-module-title">{mod.title}</div>
                <div className="home-module-desc">{mod.desc}</div>
              </div>
              {mod.adminOnly && (
                <span className="home-module-admin-tag">Admin</span>
              )}
              <div className="home-module-arrow">→</div>
            </a>
          ))}
        </div>
      </main>

    </div>
  );
}
