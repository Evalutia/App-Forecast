using System;
using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public interface IVentaRepository
  {
    // Operaciones básicas de datos - CRUD
    (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize
    );

    (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize
    );

    IReadOnlyList<string> DistinctSkus(string? filtro);
    
    // Datos brutos para cálculos en el service
    IQueryable<VentaHistorica> GetVentasBySku(string sku);
    IQueryable<VentaHistorica> GetAllVentas();
    IQueryable<Prediccion> GetAllPredicciones();
  }
}
