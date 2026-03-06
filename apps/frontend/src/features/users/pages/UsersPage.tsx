import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useUsuariosList, useBorrarAdministradorPorCorreo } from '../hooks/useUsers';
import AddAdminModal from '../components/AddAdminModal';
import AddOwnerModal from '../components/AddOwnerModal';
import EditUserModal from '../components/EditUserModal';
import BackToDashboardButton from '../components/BackToDashboardButton';
import ScrollToTopButton from '../components/ScrollToTopButton';

export default function UsersPage() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [correo, setCorreo] = useState('');
  const [rol, setRol] = useState('');
  const [showAddAdmin, setShowAddAdmin] = useState(false);
  const [showAddOwner, setShowAddOwner] = useState(false);
  const [editUserId, setEditUserId] = useState<number | null>(null);

  const { data, isLoading } = useUsuariosList({
    page,
    pageSize,
    correo: correo || undefined,
    rol: rol || undefined,
  });

  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize]);

  const borrarAdmin = useBorrarAdministradorPorCorreo();

  const handleDelete = async (correoUser: string) => {
    if (!confirm(`¿Eliminar administrador ${correoUser}?`)) return;
    try {
      await borrarAdmin.mutateAsync(correoUser);
      toast.success('Administrador eliminado.');
    } catch (e: any) {
      if (!e?.normalizedMessage) toast.error('No se pudo eliminar.');
    }
  };

  const cols = 4;

  return (
    <div className="predicciones-page">
      <div className="predicciones-header">
        <a href="/home" className="predicciones-brand">Evalutia</a>
        <div className="predicciones-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="predicciones-container">
        <header className="section-head">
          <h1 className="section-title">Administración de usuarios</h1>
          <p className="section-subtitle">Gestioná los usuarios registrados y sus roles.</p>
        </header>

        <section className="card filters-card predicciones-filtros">
          <div className="filters-grid">
            <div className="form-row">
              <label className="label">Correo</label>
              <input
                className="input"
                placeholder="Buscar por correo..."
                value={correo}
                onChange={(e) => { setCorreo(e.target.value); setPage(1); }}
              />
            </div>
            <div className="form-row">
              <label className="label">Rol</label>
              <select
                className="select"
                value={rol}
                onChange={(e) => { setRol(e.target.value); setPage(1); }}
              >
                <option value="">Todos los roles</option>
                <option value="administrador">Administrador</option>
                <option value="duenoDeEmpresa">Dueño de Empresa</option>
              </select>
            </div>
            <div className="form-row">
              <label className="label">Agregar usuario</label>
              <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                <button type="button" className="button" onClick={() => setShowAddAdmin(true)}>
                  + Administrador
                </button>
                <button type="button" className="button" onClick={() => setShowAddOwner(true)}>
                  + Dueño de empresa
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="card table-card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Correo</th>
                  <th>Rol</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i}>
                      {Array.from({ length: cols }).map((__, j) => (
                        <td key={j}><span className="skeleton skel-20" /></td>
                      ))}
                    </tr>
                  ))
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={cols} className="muted" style={{ textAlign: 'center', padding: '1.2rem 0' }}>
                      Sin resultados.
                    </td>
                  </tr>
                ) : (
                  items.map((u) => (
                    <tr key={u.id}>
                      <td className="mono">{u.id}</td>
                      <td>{u.correo}</td>
                      <td>
                        <span style={{
                          display: 'inline-block',
                          padding: '.2rem .55rem',
                          borderRadius: '.45rem',
                          fontSize: '.78rem',
                          fontWeight: 700,
                          background: u.rol === 'administrador' ? '#ecfdf5' : '#eff6ff',
                          color: u.rol === 'administrador' ? '#065f46' : '#1e40af',
                          border: `1px solid ${u.rol === 'administrador' ? '#a7f3d0' : '#bfdbfe'}`,
                        }}>
                          {u.rol}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '.4rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            className="pager-btn"
                            style={{ padding: '.3rem .65rem', fontSize: '.78rem', borderRadius: '.5rem' }}
                            onClick={() => setEditUserId(u.id)}
                          >
                            Cambiar rol/contraseña
                          </button>
                          {u.rol === 'administrador' && (
                            <button
                              type="button"
                              style={{
                                padding: '.3rem .65rem',
                                fontSize: '.78rem',
                                borderRadius: '.5rem',
                                border: '1px solid rgba(239,68,68,.35)',
                                background: '#fef2f2',
                                color: '#991b1b',
                                cursor: 'pointer',
                                fontWeight: 600,
                              }}
                              onClick={() => handleDelete(u.correo)}
                            >
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

          <div className="pager">
            <div>Página {page} de {totalPages} — Total: <strong>{total}</strong></div>
            <div className="pager-buttons">
              <button className="pager-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Anterior</button>
              <button className="pager-btn" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Siguiente</button>
            </div>
          </div>
          <div style={{ marginTop: '.5rem' }} className="muted">
            Filas por página:&nbsp;
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </section>
      </div>

      {showAddAdmin && <AddAdminModal onClose={() => setShowAddAdmin(false)} />}
      {showAddOwner && <AddOwnerModal onClose={() => setShowAddOwner(false)} />}
      {editUserId != null && <EditUserModal userId={editUserId} onClose={() => setEditUserId(null)} />}
      <ScrollToTopButton />
    </div>
  );
}
