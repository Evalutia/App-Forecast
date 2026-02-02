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
                .FromSqlInterpolated($"SELECT * FROM articulos WHERE sku = {sku} LIMIT 1")
                .AsNoTracking()
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

      return _db.Articulos
                .FromSqlInterpolated($@"
SELECT *
FROM articulos
WHERE
  ({familyId} IS NULL AND {genreId} IS NULL)
  OR (({familyId} IS NOT NULL AND familia_id = {familyId})
      OR ({genreId} IS NOT NULL AND genero_id = {genreId}))
ORDER BY sku
LIMIT {pageSize} OFFSET {offset}")
                .AsNoTracking()
                .ToList();
    }
  }
}
