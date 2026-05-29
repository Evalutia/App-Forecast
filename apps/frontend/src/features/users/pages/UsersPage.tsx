import { useMemo, useRef, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useUsuariosList, useBorrarAdministradorPorCorreo } from '../hooks/useUsers';
import AddAdminModal from '../components/AddAdminModal';
import AddOwnerModal from '../components/AddOwnerModal';
import EditUserModal from '../components/EditUserModal';
import '../../../styles/dark-layout.css';

export default function UsersPage() {
  const [page, setPage]         = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [correo, setCorreo]     = useState('');
  const [rol, setRol]           = useState('');
  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [showAddOwner, setShowAddOwner] = useState(false);
  const [editUserId, setEditUserId]     = useState<number | null>(null);

  const filterRef = useRef<HTMLElement | null>(null);
  const tableRef  = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const els = [filterRef.current, tableRef.current].filter(Boolean) as HTMLElement[];
    const obs = new IntersectionObserver(
      entries => entries.forEach(e => { if (e.isIntersecting) { (e.target as HTMLElement).classList.add('visible'); obs.unobserve(e.target); } }),
      { threshold: 0.04 }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  const { data, isLoading } = useUsuariosList({ page, pageSize, correo: correo || undefined, rol: rol || undefined });
  const total      = data?.total ?? 0;
  const items      = data?.items ?? [];
  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);
  const borrarAdmin = useBorrarAdministradorPorCorreo();

  const handleDelete = async (correoUser: string) => {
    if (!confirm(`¿Eliminar administrador ${correoUser}?`)) return;
    try {
      await borrarAdmin.mutateAsync(correoUser);
      toast.success('Administrador eliminado.');
    } catch (e: unknown) {
      if (!(e as { normalizedMessage?: string })?.normalizedMessage) toast.error('No se pudo eliminar.');
    }
  };

  return (
    <div className="pg-page">

      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Usuarios</h1>
          <p className="pg-subtitle">Gestioná los accesos y roles de la plataforma.</p>
          {total > 0 && <div className="pg-stat-pill">{total} usuarios</div>}
        </div>
      </section>

      <div className="pg-container">

        {/* Filtros + acciones */}
        <section className="pg-filter-card pg-reveal" ref={filterRef}>
          <div className="pg-filters-grid">
            <div className="pg-form-row">
              <label className="pg-label">Correo</label>
              <input className="pg-input" placeholder="Buscar por correo…" value={correo}
                onChange={e => { setCorreo(e.target.value); setPage(1); }} />
            </div>
            <div className="pg-form-row">
              <label className="pg-label">Rol</label>
              <select className="pg-select" value={rol} onChange={e => { setRol(e.target.value); setPage(1); }}>
                <option value="">Todos los roles</option>
                <option value="administrador">Administrador</option>
                <option value="duenoDeEmpresa">Dueño de Empresa</option>
              </select>
            </div>
          </div>
          <div className="pg-filter-actions">
            <button type="button" className="pg-btn" onClick={() => setShowAddAdmin(true)}>+ Administrador</button>
            <button type="button" className="pg-btn-ghost" onClick={() => setShowAddOwner(true)}>+ Dueño de empresa</button>
          </div>
        </section>

        {/* Tabla */}
        <section className="pg-table-card pg-reveal" ref={tableRef}>
          <div className="pg-table-wrap">
            <table className="pg-table">
              <thead>
                <tr>
                  <th className="pg-th-key">ID</th>
                  <th>Correo</th>
                  <th>Rol</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      <td><span className="pg-skeleton pg-skeleton-sm" /></td>
                      <td><span className="pg-skeleton pg-skeleton-lg" /></td>
                      <td><span className="pg-skeleton pg-skeleton-md" /></td>
                      <td><span className="pg-skeleton pg-skeleton-md" /></td>
                    </tr>
                  ))
                ) : items.length === 0 ? (
                  <tr><td colSpan={4} className="pg-empty">Sin resultados.</td></tr>
                ) : (
                  items.map(u => (
                    <tr key={u.id}>
                      <td className="pg-td-key">{u.id}</td>
                      <td className="pg-td-desc">{u.correo}</td>
                      <td>
                        <span className={u.rol === 'administrador' ? 'pg-badge pg-badge-green' : 'pg-badge pg-badge-blue'}>
                          {u.rol === 'administrador' ? 'Administrador' : 'Dueño de Empresa'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                          <button type="button" className="pg-btn pg-btn-sm pg-btn-ghost"
                            onClick={() => setEditUserId(u.id)}>
                            Editar
                          </button>
                          {u.rol === 'administrador' && (
                            <button type="button" className="pg-btn-danger"
                              onClick={() => handleDelete(u.correo)}>
                              Eliminar
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="pg-pager">
            <span className="pg-pager-info">Página <strong>{page}</strong> de <strong>{totalPages}</strong> — Total: <strong>{total}</strong></span>
            <div className="pg-pager-right">
              <select className="pg-page-size-select" value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}>
                {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n} filas</option>)}
              </select>
              <button className="pg-pager-btn" disabled={page <= 1}          onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="pg-pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
        </section>

      </div>

      {showAddAdmin && <AddAdminModal onClose={() => setShowAddAdmin(false)} />}
      {showAddOwner && <AddOwnerModal onClose={() => setShowAddOwner(false)} />}
      {editUserId != null && <EditUserModal userId={editUserId} onClose={() => setEditUserId(null)} />}
    </div>
  );
}
