using System;
using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public interface IVentaRepository
  {
    // Histórico: registros crudos con filtros + paginación
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    // Agregado: ventas agrupadas por período (mensual, anual o por fecha)
    (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,   // "mensual", "anual" o default (por fecha)
        int page,
        int pageSize
    );

    // Autocomplete de SKUs
    IReadOnlyList<string> DistinctSkus(string? filtro);
  }
}
