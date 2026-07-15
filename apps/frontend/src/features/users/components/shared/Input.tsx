interface InputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: 'text' | 'email' | 'password';
  required?: boolean;
}

export default function Input({ label, value, onChange, type = 'text', required = true }: InputProps) {
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
