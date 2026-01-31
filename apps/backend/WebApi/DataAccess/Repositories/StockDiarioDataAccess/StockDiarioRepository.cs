using Microsoft.EntityFrameworkCore;
using System;
using System.Collections.Generic;
using System.Data;
using System.Data.Common;
using System.Linq;
using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.StockDiarioDataAccess
{
  public class StockDiarioRepository : IStockDiarioRepository
  {
    private readonly EvalutiaDbContext _db;

    public StockDiarioRepository(EvalutiaDbContext db)
    {
      _db = db;
    }

    public void InsertBatch(IEnumerable<StockDiario> records)
    {
      if (records is null) throw new ArgumentNullException(nameof(records));

      var list = records as IList<StockDiario> ?? records.ToList();
      if (list.Count == 0) return;

      using var tx = _db.Database.BeginTransaction();
      try
      {
        const int chunkSize = 200;

        for (var i = 0; i < list.Count; i += chunkSize)
        {
          var chunk = list.Skip(i).Take(chunkSize).ToList();
          ExecuteUpsertChunk(chunk, tx.GetDbTransaction());
        }

        tx.Commit();
      }
      catch
      {
        tx.Rollback();
        throw;
      }
    }

    public IEnumerable<(DateOnly Fecha, uint CantidadTotal)> GetDailySumBySkuAndMonth(string sku, int year, int month)
    {
      if (string.IsNullOrWhiteSpace(sku)) throw new ArgumentException("sku is required", nameof(sku));
      if (year < 1) throw new ArgumentOutOfRangeException(nameof(year));
      if (month is < 1 or > 12) throw new ArgumentOutOfRangeException(nameof(month));

      var conn = _db.Database.GetDbConnection();
      if (conn.State != ConnectionState.Open)
        conn.Open();

      using var cmd = conn.CreateCommand();
      cmd.CommandText = @"
SELECT fecha AS Fecha,
       CAST(SUM(cantidad) AS UNSIGNED) AS CantidadTotal
FROM stock_diario
WHERE sku = @sku
  AND YEAR(fecha) = @year
  AND MONTH(fecha) = @month
GROUP BY fecha
ORDER BY fecha;";

      AddParam(cmd, "@sku", sku);
      AddParam(cmd, "@year", year);
      AddParam(cmd, "@month", month);

      var result = new List<(DateOnly Fecha, uint CantidadTotal)>();
      using var reader = cmd.ExecuteReader();
      while (reader.Read())
      {
        DateOnly fecha;
        var fechaObj = reader.GetValue(0);
        if (fechaObj is DateTime dt)
          fecha = DateOnly.FromDateTime(dt);
        else
          fecha = reader.GetFieldValue<DateOnly>(0);
        var cantidadTotal = Convert.ToUInt32(reader.GetValue(1));
        result.Add((fecha, cantidadTotal));
      }

      return result;
    }

    private void ExecuteUpsertChunk(IReadOnlyList<StockDiario> chunk, DbTransaction dbTransaction)
    {
      var conn = _db.Database.GetDbConnection();
      if (conn.State != ConnectionState.Open)
        conn.Open();

      using var cmd = conn.CreateCommand();
      cmd.Transaction = dbTransaction;

      var valuesParts = new List<string>(chunk.Count);

      for (var i = 0; i < chunk.Count; i++)
      {
        var r = chunk[i];

        var pSku = $"@sku{i}";
        var pFecha = $"@fecha{i}";
        var pCantidad = $"@cantidad{i}";
        var pDeposito = $"@deposito{i}";
        var pFuente = $"@fuente{i}";
        var pTs = $"@ts{i}";

        valuesParts.Add($"({pSku}, {pFecha}, {pCantidad}, {pDeposito}, {pFuente}, {pTs})");

        AddParam(cmd, pSku, r.Sku);
        AddParam(cmd, pFecha, r.Fecha);
        AddParam(cmd, pCantidad, r.Cantidad);
        AddParam(cmd, pDeposito, (object?)r.DepositoId ?? DBNull.Value);
        AddParam(cmd, pFuente, (object?)r.Fuente ?? DBNull.Value);
        AddParam(cmd, pTs, r.TsCarga);
      }

      cmd.CommandText = $@"
INSERT INTO stock_diario (sku, fecha, cantidad, deposito_id, fuente, ts_carga)
VALUES {string.Join(",", valuesParts)}
ON DUPLICATE KEY UPDATE
  cantidad = VALUES(cantidad),
  fuente = VALUES(fuente),
  ts_carga = VALUES(ts_carga);";

      cmd.ExecuteNonQuery();
    }

    private static void AddParam(DbCommand cmd, string name, object value)
    {
        var p = cmd.CreateParameter();
        p.ParameterName = name;

        if (value is DateOnly d)
        {
            // Convertir DateOnly a DateTime para el driver y marcar DbType.Date
            p.Value = d.ToDateTime(TimeOnly.MinValue);
            p.DbType = DbType.Date;
        }
        else if (value is DateTime dt)
        {
            p.Value = dt;
            p.DbType = DbType.DateTime;
        }
        else if (value is uint || value is UInt32)
        {
            p.Value = Convert.ToUInt32(value);
            p.DbType = DbType.UInt32;
        }
        else if (value is ulong || value is UInt64)
        {
            p.Value = Convert.ToUInt64(value);
            // Algunos providers no tienen DbType.UInt64; usar UInt64 si lo soporta, si no usar Int64
            p.DbType = DbType.UInt64;
        }
        else if (value is ushort || value is UInt16)
        {
            p.Value = Convert.ToUInt16(value);
            p.DbType = DbType.UInt16;
        }
        else if (value is byte || value is Byte)
        {
            p.Value = Convert.ToByte(value);
            p.DbType = DbType.Byte;
        }
        else if (value is int || value is Int32)
        {
            p.Value = Convert.ToInt32(value);
            p.DbType = DbType.Int32;
        }
        else if (value is long || value is Int64)
        {
            p.Value = Convert.ToInt64(value);
            p.DbType = DbType.Int64;
        }
        else if (value is decimal || value is Decimal)
        {
            p.Value = Convert.ToDecimal(value);
            p.DbType = DbType.Decimal;
        }
        else if (value is bool)
        {
            p.Value = (bool)value ? 1 : 0;
            p.DbType = DbType.Int32;
        }
        else if (value is string)
        {
            p.Value = (object?)value ?? DBNull.Value;
            p.DbType = DbType.String;
        }
        else
        {
            p.Value = value ?? DBNull.Value;
        }

        cmd.Parameters.Add(p);
    }
  }
}
