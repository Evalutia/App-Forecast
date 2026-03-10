using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.Linq;
using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.ArticuloDataAccess
{
  public class ArticuloRepository : IArticuloRepository
  {
    private readonly EvalutiaDbContext _db;

    public ArticuloRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public Articulo? FindBySku(string sku)
    {
      if (string.IsNullOrWhiteSpace(sku)) return null;

      return _db.Articulos
                .AsNoTracking()
                .Where(a => a.Sku == sku)
                .FirstOrDefault();
    }

    public Articulo Upsert(Articulo articulo)
    {
      if (articulo is null) throw new ArgumentNullException(nameof(articulo));

      // Obtener la estrategia de ejecución del DbContext (soporta reintentos)
      var strategy = _db.Database.CreateExecutionStrategy();

      // Ejecutar todo el bloque (transacción + operaciones) dentro de la estrategia
      return strategy.Execute(() =>
      {
        using var tx = _db.Database.BeginTransaction();
        try
        {
          _db.Database.ExecuteSqlInterpolated($@"
INSERT INTO articulos
 (sku, barcode, descripcion, familia_id, familia_nombre, genero_id, genero_descripcion, stock_minimo, frecuencia_mensual, fuente)
VALUES
 ({articulo.Sku}, {articulo.Barcode}, {articulo.Descripcion}, {articulo.FamiliaId}, {articulo.FamiliaNombre}, {articulo.GeneroId}, {articulo.GeneroDescripcion}, {articulo.StockMinimo}, {articulo.FrecuenciaMensual}, {articulo.Fuente})
ON DUPLICATE KEY UPDATE
 barcode = VALUES(barcode),
 descripcion = VALUES(descripcion),
 familia_id = VALUES(familia_id),
 familia_nombre = VALUES(familia_nombre),
 genero_id = VALUES(genero_id),
 genero_descripcion = VALUES(genero_descripcion),
 stock_minimo = VALUES(stock_minimo),
 frecuencia_mensual = VALUES(frecuencia_mensual),
 fuente = VALUES(fuente);");

          var saved = FindBySku(articulo.Sku);
          if (saved is null)
            throw new InvalidOperationException($"Upsert failed for sku '{articulo.Sku}'.");

          tx.Commit();
          return saved;
        }
        catch
        {
          try { tx.Rollback(); } catch { /* swallow rollback errors */ }
          throw;
        }
      });
    }

    public IEnumerable<Articulo> FindByFamilyOrGenre(int? familyId, int? genreId, int page, int pageSize)
    {
      page = Math.Max(1, page);
      pageSize = Math.Max(1, pageSize);

      if (familyId.HasValue && familyId.Value < 0) familyId = null;
      if (genreId.HasValue && genreId.Value < 0) genreId = null;

      var offset = (page - 1) * pageSize;

      var query = _db.Articulos.AsNoTracking().AsQueryable();

      if (familyId.HasValue && familyId.Value >= 0)
      {
        query = query.Where(a => a.FamiliaId == familyId.Value);
      }
      if (genreId.HasValue && genreId.Value >= 0)
      {
        query = query.Where(a => a.GeneroId == genreId.Value);
      }

      return query.OrderBy(a => a.Sku).Skip(offset).Take(pageSize).ToList();
    }

    public int CountByFamilyOrGenre(int? familyId, int? genreId)
    {
      if (familyId.HasValue && familyId.Value < 0) familyId = null;
      if (genreId.HasValue && genreId.Value < 0) genreId = null;

      var query = _db.Articulos.AsNoTracking().AsQueryable();
      if (familyId.HasValue)
      {
        query = query.Where(a => a.FamiliaId == familyId.Value);
      }
      if (genreId.HasValue)
      {
        query = query.Where(a => a.GeneroId == genreId.Value);
      }

      return query.Count();
    }

    public (IReadOnlyList<Articulo> Items, int Total) Search(string? sku, string? familiaNombre, string? generoDescripcion, int page, int pageSize)
    {
      page = Math.Max(1, page);
      pageSize = Math.Clamp(pageSize, 1, 200);

      var q = _db.Articulos.AsNoTracking().AsQueryable();

      if (!string.IsNullOrWhiteSpace(sku))
        q = q.Where(a => a.Sku.ToLower().StartsWith(sku.ToLower()));

      if (!string.IsNullOrWhiteSpace(familiaNombre))
        q = q.Where(a => a.FamiliaNombre == familiaNombre);

      if (!string.IsNullOrWhiteSpace(generoDescripcion))
        q = q.Where(a => a.GeneroDescripcion == generoDescripcion);

      var total = q.Count();
      var items = q.OrderBy(a => a.Sku)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();

      return (items, total);
    }

    public IReadOnlyList<string> DistinctFamilias()
    {
      return _db.Articulos
                .AsNoTracking()
                .Where(a => a.FamiliaNombre != null && a.FamiliaNombre != "")
                .Select(a => a.FamiliaNombre!)
                .Distinct()
                .OrderBy(f => f)
                .ToList();
    }

    public IReadOnlyList<string> DistinctGeneros()
    {
      return _db.Articulos
                .AsNoTracking()
                .Where(a => a.GeneroDescripcion != null && a.GeneroDescripcion != "")
                .Select(a => a.GeneroDescripcion!)
                .Distinct()
                .OrderBy(g => g)
                .ToList();
    }
  }
}
