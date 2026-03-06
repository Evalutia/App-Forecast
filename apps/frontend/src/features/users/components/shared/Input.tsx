export default function Input({ label, value, onChange, type = 'text', required = true }: any) {
  return (
    <div className="form-row" style={{ alignItems: 'flex-start', marginBottom: '.85rem' }}>
      <label className="label" style={{ textAlign: 'left' }}>{label}</label>
      <input
        type={type}
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      />
    </div>
  );
}
