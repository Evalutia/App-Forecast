export default function Modal({ title, onClose, children, maxWidth = '28rem' }: any) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(2,44,34,.55)', backdropFilter: 'blur(4px)', padding: '1rem',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        width: '100%', maxWidth,
        background: 'rgba(255,255,255,.97)',
        border: '1px solid rgba(209,250,229,.4)',
        borderRadius: '1.5rem',
        padding: '1.75rem',
        boxShadow: '0 25px 40px rgba(2,44,34,.22)',
        color: 'var(--emerald-950)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <h3 style={{ margin: 0, fontFamily: "'Montserrat', sans-serif", fontWeight: 900, fontSize: '1.2rem', color: 'var(--emerald-950)' }}>
            {title}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: '1px solid rgba(16,185,129,.25)',
              borderRadius: '.5rem', width: '2rem', height: '2rem',
              cursor: 'pointer', color: '#6b7280', fontSize: '1rem',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
