using System;
using WebApi.Models;

namespace Models.Validators
{
  public static class PrediccionValidator
  {
    public static void Validacion(Prediccion prediccion)
    {
      ValidarFecha(prediccion.FechaPredicha);
      ValidarCantidad(prediccion.CantidadPredicha);
    }

    private static void ValidarFecha(DateOnly fechaPredicha)
    {
      if (fechaPredicha < DateOnly.FromDateTime(DateTime.Today))
        throw new ArgumentException("La fecha predicha debe ser hoy o una fecha futura.", nameof(fechaPredicha));
    }

    private static void ValidarCantidad(decimal cantidadPredicha)
    {
      if (cantidadPredicha < 0)
        throw new ArgumentException("La cantidad predicha no puede ser negativa.", nameof(cantidadPredicha));
    }
  }
}
