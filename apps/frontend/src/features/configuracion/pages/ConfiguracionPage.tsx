import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useUmbralesTickets, useUpdateUmbralesTickets } from '../hooks/useConfiguracion';
import Input from '../../users/components/shared/Input';
import '../../../styles/dark-layout.css';

export default function ConfiguracionPage() {
  const { data, isLoading } = useUmbralesTickets();
  const actualizar = useUpdateUmbralesTickets();

  const [ticketsBajoMax, setTicketsBajoMax] = useState('');
  const [ticketsAltoMin, setTicketsAltoMin] = useState('');

  useEffect(() => {
    if (data) {
      setTicketsBajoMax(String(data.ticketsBajoMax));
      setTicketsAltoMin(String(data.ticketsAltoMin));
    }
  }, [data]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const bajo = Number(ticketsBajoMax);
    const alto = Number(ticketsAltoMin);

    if (!Number.isInteger(bajo) || !Number.isInteger(alto) || bajo <= 0 || alto <= 0) {
      toast.error('Los umbrales deben ser números enteros mayores a 0.');
      return;
    }
    if (bajo >= alto) {
      toast.error('El umbral bajo debe ser menor que el umbral alto.');
      return;
    }

    try {
      await actualizar.mutateAsync({ ticketsBajoMax: bajo, ticketsAltoMin: alto });
      toast.success('Umbrales actualizados.');
    } catch {
      // el interceptor de axios ya muestra el toast de error
    }
  };

  return (
    <div className="pg-page">
      <section className="pg-hero">
        <div className="pg-hero-grid" />
        <div className="pg-hero-glow" />
        <div className="pg-hero-content">
          <h1 className="pg-title">Configuración</h1>
          <p className="pg-subtitle">Umbrales de frecuencia de venta usados en la Planilla de Reposición.</p>
        </div>
      </section>

      <section className="card" style={{ maxWidth: 480, margin: '1.5rem auto' }}>
        {isLoading ? (
          <p>Cargando…</p>
        ) : (
          <form onSubmit={onSubmit}>
            <p style={{ marginBottom: '1rem', color: 'var(--text-muted, #888)' }}>
              Definen cuántos días con venta en el mes (tickets) tiene que tener un SKU para
              usar el promedio histórico, el promedio de ambos, o la venta real del mes.
            </p>

            <Input
              label="Umbral bajo (≤, usa Histórico)"
              value={ticketsBajoMax}
              onChange={setTicketsBajoMax}
            />
            <Input
              label="Umbral alto (≥, usa Venta Real)"
              value={ticketsAltoMin}
              onChange={setTicketsAltoMin}
            />

            <p style={{ margin: '1rem 0', fontSize: '.85rem', color: 'var(--text-muted, #888)' }}>
              Los cambios se aplican en el próximo cálculo nocturno de la Planilla — no se
              reflejan al instante.
            </p>

            <div className="filters-actions" style={{ justifyContent: 'flex-end' }}>
              <button type="submit" className="button" disabled={actualizar.isPending}>
                {actualizar.isPending ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
