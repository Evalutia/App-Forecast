# pulir-ventana

Transformás una ventana del frontend al estilo visual de Evalutia.

## Cómo usarlo

```
/pulir-ventana <nombre-de-la-feature>
```

Ejemplo: `/pulir-ventana planilla`

El argumento es el nombre de la feature tal como aparece en `src/features/` (ej. `planilla`, `jobs`, `resultados`).

---

## Qué hace este comando

1. Lee el archivo de la página principal (`src/features/<feature>/pages/<Feature>Page.tsx`)
2. Lee el CSS actual (`src/styles/<feature>.css`) si existe
3. Lee `src/styles/sales.css` como referencia del design system global
4. Identifica qué falta o está roto respecto al estilo Evalutia
5. Aplica las transformaciones necesarias al TSX y al CSS
6. Si el CSS no existe, lo crea completo desde cero

---

## Sistema de diseño Evalutia (referencia canónica)

### Variables CSS globales (definidas en sales.css)

```css
:root {
  --emerald-50:  #ecfdf5;
  --emerald-100: #d1fae5;
  --emerald-200: #a7f3d0;
  --emerald-900: #064e3b;
  --emerald-950: #022c22;
  --white: #ffffff;
  --black: #000000;
  --border: rgba(209, 250, 229, .4);
  --shadow: 0 25px 40px rgba(2, 44, 34, .18);
  --muted: rgba(6, 78, 59, .72);
  --content-max: 80rem;
  --shadow-strong: 0 6px 18px rgba(0,0,0,.12);
  --shadow-soft-inset: 0 1px 0 rgba(255,255,255,.06) inset;
}
```

### Template CSS por página (sustituir `{P}` por el prefijo de la feature)

```css
/* === Página === */
.{P}-page {
  min-height: 100dvh;
  background: linear-gradient(135deg, var(--emerald-950), var(--emerald-900), var(--emerald-950));
  background-attachment: fixed;
  background-repeat: no-repeat;
  background-size: cover;
}

/* === Header === */
.{P}-header {
  width: 100%;
  margin: 0;
  padding: .75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--white);
  border-bottom: 1px solid rgba(0,0,0,.06);
  border-radius: 0;
  box-shadow: var(--shadow-strong);
}

/* === Brand (logo Evalutia) === */
.{P}-brand {
  background: none;
  border: 0;
  border-radius: 0;
  padding: 0;
  color: var(--emerald-950);
  font-family: 'Montserrat', sans-serif;
  font-size: 1.25rem;
  font-weight: 900;
  letter-spacing: .18em;
  text-transform: uppercase;
  line-height: 1.05;
  text-decoration: none;
  cursor: pointer;
}
.{P}-brand:hover { color: var(--emerald-900); }

/* === Acciones del header === */
.{P}-actions {
  display: flex;
  align-items: center;
  gap: .5rem;
}
.{P}-actions :where(a, button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  padding: .375rem .75rem;
  border-radius: .5rem;
  background: rgba(2, 44, 34, .92);
  border: 1px solid rgba(2, 44, 34, 1);
  color: var(--white);
  font-size: .85rem;
  font-weight: 700;
  text-decoration: none;
  transition: background .15s ease, transform .06s ease, box-shadow .15s ease;
  box-shadow: var(--shadow-soft-inset), 0 6px 14px rgba(0,0,0,.12);
  cursor: pointer;
}
.{P}-actions :where(a, button):hover { background: var(--emerald-900); }
.{P}-actions :where(a, button):active { transform: translateY(1px); }
.{P}-actions :where(a[disabled], button:disabled) { opacity: .6; cursor: not-allowed; }

/* === Contenedor principal === */
.{P}-container {
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 1.5rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 1rem;
}
.{P}-container section.card {
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
}
```

### Template JSX por página

```tsx
import BackToDashboardButton from '../../users/components/BackToDashboardButton';
import ScrollToTopButton from '../../users/components/ScrollToTopButton';
import '../../../../styles/{P}.css';

export default function {Feature}Page() {
  return (
    <div className="{P}-page">
      <div className="{P}-header">
        <a href="/home" className="{P}-brand">Evalutia</a>
        <div className="{P}-actions">
          <BackToDashboardButton />
        </div>
      </div>

      <div className="{P}-container">
        <header className="section-head">
          <h1 className="section-title">{Título}</h1>
          <p className="section-subtitle">{Subtítulo descriptivo}</p>
        </header>

        {/* subsecciones con <h2 className="subsection-title"> y <div className="section-divider"> entre ellas */}
      </div>

      <ScrollToTopButton />
    </div>
  );
}
```

### Clases reutilizables globales (disponibles en todos los contextos)

| Clase | Uso |
|-------|-----|
| `.card` | Contenedor blanco semi-transparente con blur y sombra |
| `.table` | Tabla con sticky header verde, hover rows |
| `.table thead th.sku-column` | Cabecera SKU con gradiente verde oscuro |
| `.table tbody td.sku-column` | Celda SKU con fondo verde suave |
| `.button` | Botón primario verde oscuro, uppercase |
| `.button.button-ghost` | Botón borde verde, fondo transparente |
| `.export-btn` | Botón "Descargar Excel" |
| `.pager-btn` | Botones de paginación |
| `.input` / `.select` | Campos de formulario con foco verde |
| `.label` | Label uppercase, 0.8rem, 800 weight |
| `.section-head` | Wrapper del título principal |
| `.section-title` | h1 blanco fluido (`clamp(2rem, 1.4vw + 1.6rem, 2.75rem)`) |
| `.section-subtitle` | p blanco semi-transparente bajo el h1 |
| `.subsection-title` | h2 con gradiente blanco y borde inferior verde |
| `.section-divider` | Línea separadora con gradiente verde |
| `.filters-card` | Card de filtros con flex-wrap |
| `.filters-grid` | Grid 3 columnas para filtros (responsive) |
| `.skeleton` | Placeholder de carga animado |

### Badges de estado (Tailwind inline)

```tsx
// Jobs / estados de proceso
const badgeClasses = {
  en_cola:   'bg-gray-100 text-gray-800 ring-1 ring-gray-200',
  ejecutando:'bg-blue-100 text-blue-800 ring-1 ring-blue-200',
  exitoso:   'bg-green-100 text-green-800 ring-1 ring-green-200',
  fallido:   'bg-red-100 text-red-800 ring-1 ring-red-200',
};
// Estructura: <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full ${cls}`}>

// Severidad / análisis
const severityStyle = (rate: number) => ({
  color: rate > 30 ? '#dc2626' : rate > 15 ? '#d97706' : '#16a34a',
  background: rate > 30 ? '#fef2f2' : rate > 15 ? '#fffbeb' : '#f0fdf4',
  border: `1px solid ${rate > 30 ? '#dc262620' : rate > 15 ? '#d9770620' : '#16a34a20'}`,
  padding: '0.15rem 0.5rem',
  borderRadius: '0.375rem',
  fontSize: '0.7rem',
  fontWeight: 800,
});
```

### Paginación estándar

```tsx
<div style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:'1rem', marginTop:'1rem' }}>
  <button className="pager-btn" onClick={irAnterior} disabled={page === 1}>← Anterior</button>
  <span style={{ color:'var(--muted)', fontSize:'0.9rem', fontWeight:600 }}>
    Página {page} de {totalPages}
  </span>
  <button className="pager-btn" onClick={irSiguiente} disabled={page >= totalPages}>Siguiente →</button>
</div>
```

---

## Checklist de verificación tras aplicar

Después de transformar una ventana, verificá:

- [ ] El fondo de la página es el gradiente esmeralda oscuro
- [ ] El header tiene fondo blanco con el logo "EVALUTIA" en Montserrat y el botón "Back to Dashboard"
- [ ] El contenedor tiene `max-width: 80rem` y `margin: 0 auto`
- [ ] El `section-title` es blanco y fluido
- [ ] Las cards son blancas semi-transparentes con `backdrop-filter: blur(6px)`
- [ ] Las tablas tienen sticky header con fondo `#f7faf9` y borde verde
- [ ] Los botones primarios son verde oscuro (`var(--emerald-900)`) con texto blanco uppercase
- [ ] El import del CSS de la feature está en la página o en el componente raíz de la feature
- [ ] `<ScrollToTopButton />` está al final del div raíz

---

## Instrucciones de ejecución

Cuando el usuario invoca `/pulir-ventana <feature>`:

1. **Leer** `src/features/<feature>/pages/` para encontrar el archivo de página principal
2. **Leer** `src/styles/<feature>.css` (si existe) para ver el estado actual
3. **Leer** `src/styles/sales.css` para confirmar las variables globales disponibles
4. **Identificar los gaps**: qué falta en el CSS y en el TSX vs el template canónico
5. **Editar o crear** `src/styles/<feature>.css` con el CSS completo para esa página (reemplazando `{P}` por el prefijo)
6. **Editar** el TSX de la página para aplicar las clases correctas
7. **Verificar** que el import del CSS está presente en el componente
8. Presentar al usuario el **resumen de cambios** y el **checklist de verificación** completo
