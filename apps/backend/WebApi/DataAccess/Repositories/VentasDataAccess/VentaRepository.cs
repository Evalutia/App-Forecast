using System;
using System.Collections.Generic;
using System.Linq;
using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.VentaDataAccess
{
  public class VentaRepository : IVentaRepository
  {
    private readonly EvalutiaDbContext _db;

    public VentaRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public (IReadOnlyList<VentaHistorica> Items, int Total) Search(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        int page,
        int pageSize)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue)
        q = q.Where(v => v.Fecha >= fechaDesde.Value);

      if (fechaHasta.HasValue)
        q = q.Where(v => v.Fecha <= fechaHasta.Value);

      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(v => v.Sku == sku);

      var total = q.Count();

      var items = q.OrderBy(v => v.Fecha)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    public (IReadOnlyList<VentaAgregada> Items, int Total) Aggregate(
        DateOnly? fechaDesde,
        DateOnly? fechaHasta,
        string? sku,
        string periodo,
        int page,
        int pageSize)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (fechaDesde.HasValue)
        q = q.Where(v => v.Fecha >= fechaDesde.Value);

      if (fechaHasta.HasValue)
        q = q.Where(v => v.Fecha <= fechaHasta.Value);

      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(v => v.Sku == sku);

      var lowerPeriodo = periodo?.ToLower();

      // Si el periodo es trimestral, para evitar translaciones inconsistentes de EF
      // materializamos los registros y agrupamos en memoria asegurando UNA fila por (Year,Quarter).
      if (lowerPeriodo == "trimestral")
      {
        var rows = q.ToList(); // materializa
        var grouped = rows
            .GroupBy(v => new { Year = v.Fecha.Year, Quarter = (v.Fecha.Month - 1) / 3 + 1, v.Sku })
            .Select(g => new
            {
              Year = g.Key.Year,
              Month = 0,
              Day = 0,
              Sku = g.Key.Sku,
              TotalCantidad = (uint)g.Sum(x => (long)x.Cantidad),
              Quarter = g.Key.Quarter
            })
            .OrderByDescending(x => x.Year)
            .ThenByDescending(x => x.Quarter)
            .ToList();

        var total = grouped.Count();
        var pageItems = grouped
            .OrderBy(x => x.Year)
            .ThenBy(x => x.Quarter)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToList();

        var items = pageItems.Select(x => new VentaAgregada
        {
          Periodo = $"{x.Year:D4}-Q{x.Quarter}",
          Sku = x.Sku,
          TotalCantidad = x.TotalCantidad
        }).ToList();

        return (items, total);
      }

      // Para los otros periodos usamos la agrupación traducida por EF (mensual/anual/dia)
      var agrupado = lowerPeriodo == "mensual"
        ? q.GroupBy(v => new { v.Sku, Year = v.Fecha.Year, Month = v.Fecha.Month })
            .Select(g => new
            {
              Year = g.Key.Year,
              Month = g.Key.Month,
              Day = 1,
              Sku = g.Key.Sku,
              TotalCantidad = (uint)g.Sum(x => x.Cantidad),
              Quarter = 0
            })
        : lowerPeriodo == "anual"
          ? q.GroupBy(v => new { v.Sku, Year = v.Fecha.Year })
              .Select(g => new
              {
                Year = g.Key.Year,
                Month = 0,
                Day = 0,
                Sku = g.Key.Sku,
                TotalCantidad = (uint)g.Sum(x => x.Cantidad),
                Quarter = 0
              })
          : q.GroupBy(v => new { v.Sku, Fecha = v.Fecha })
              .Select(g => new
              {
                Year = g.Key.Fecha.Year,
                Month = g.Key.Fecha.Month,
                Day = g.Key.Fecha.Day,
                Sku = g.Key.Sku,
                TotalCantidad = (uint)g.Sum(x => x.Cantidad),
                Quarter = 0
              });

      var totalCount = agrupado.Count();

      var pageItemsGeneral = agrupado.OrderBy(a => a.Year)
                            .ThenBy(a => a.Month)
                            .ThenBy(a => a.Day)
                            .Skip((page - 1) * pageSize)
                            .Take(pageSize)
                            .ToList();

      List<VentaAgregada> outItems = pageItemsGeneral.Select(x => new VentaAgregada
      {
        Periodo = lowerPeriodo == "mensual"
                    ? $"{x.Year:D4}-{x.Month:D2}"
                    : lowerPeriodo == "anual"
                      ? $"{x.Year:D4}"
                      : $"{x.Year:D4}-{x.Month:D2}-{x.Day:D2}",
        Sku = x.Sku,
        TotalCantidad = x.TotalCantidad
      }).ToList();

      return (outItems, totalCount);
    }

    public IReadOnlyList<string> DistinctSkus(string? filtro)
    {
      var q = _db.VentasHistoricas.AsQueryable();

      if (!string.IsNullOrWhiteSpace(filtro))
        q = q.Where(v => v.Sku.Contains(filtro));

      return q.Select(v => v.Sku)
              .Distinct()
              .OrderBy(s => s)
              .Take(50)
              .ToList();
    }

    // Solo operaciones de datos básicos - sin lógica de negocio
    public IQueryable<VentaHistorica> GetVentasBySku(string sku)
    {
      return _db.VentasHistoricas.Where(v => v.Sku == sku);
    }

    public IQueryable<VentaHistorica> GetAllVentas()
    {
      return _db.VentasHistoricas;
    }

    public IQueryable<Prediccion> GetAllPredicciones()
    {
      return _db.Predicciones;
    }
  }
}
