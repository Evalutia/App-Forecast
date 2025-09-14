using System;
using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public interface IVentaRepository
  {
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    (IReadOnlyList<object> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo, // ej. "mensual", "anual"
        int page,
        int pageSize
    );

    IReadOnlyList<string> DistinctSkus(string? filtro);
  }
}
