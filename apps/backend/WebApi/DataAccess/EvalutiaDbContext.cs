using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;
using Pomelo.EntityFrameworkCore.MySql.Scaffolding.Internal;
using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using WebApi.Models;

namespace WebApi.Data;

public class EvalutiaDbContext : DbContext
{
  public EvalutiaDbContext()
  {
  }

  public EvalutiaDbContext(DbContextOptions<EvalutiaDbContext> options)
      : base(options)
  {
  }

  public virtual DbSet<JobHistorial> JobsHistoriales { get; set; }

  public virtual DbSet<Prediccion> Predicciones { get; set; }

  public virtual DbSet<Usuario> Usuarios { get; set; }

  public virtual DbSet<Articulo> Articulos { get; set; }

  public virtual DbSet<StockDiario> StockDiario { get; set; }

  public virtual DbSet<VentasMensuales> VentasMensuales { get; set; }

  public virtual DbSet<VentaHistorica> VentasHistoricas { get; set; }

  public virtual DbSet<PlanillaVentasCalculada> PlanillasVentasCalculadas { get; set; }

  protected override void OnModelCreating(ModelBuilder modelBuilder)
  {
    modelBuilder
        .UseCollation("utf8mb4_0900_ai_ci")
        .HasCharSet("utf8mb4");

    var dateOnlyConverter = new ValueConverter<DateOnly, DateTime>(
        d => d.ToDateTime(TimeOnly.MinValue),
        dt => DateOnly.FromDateTime(dt));

    modelBuilder.Entity<Articulo>(entity =>
    {
      entity.HasKey(e => e.Sku).HasName("PRIMARY");

      entity.ToTable("articulos");

      entity.Property(e => e.Sku)
          .HasMaxLength(120)
          .HasColumnName("sku");
      entity.Property(e => e.Barcode)
          .HasMaxLength(255)
          .HasColumnName("barcode");
      entity.Property(e => e.Descripcion)
          .HasMaxLength(512)
          .HasColumnName("descripcion");
      entity.Property(e => e.SeccionId)
          .HasColumnName("seccion_id");
      entity.Property(e => e.SeccionNombre)
          .HasMaxLength(255)
          .HasColumnName("seccion_nombre");
      entity.Property(e => e.MarcaId)
          .HasColumnName("marca_id");
      entity.Property(e => e.MarcaNombre)
          .HasMaxLength(255)
          .HasColumnName("marca_nombre");
      entity.Property(e => e.TemporadaId)
          .HasColumnName("temporada_id");
      entity.Property(e => e.TemporadaNombre)
          .HasMaxLength(255)
          .HasColumnName("temporada_nombre");
      entity.Property(e => e.FecAlta)
          .HasColumnType("datetime")
          .HasColumnName("fec_alta");
      entity.Property(e => e.FecModif)
          .HasColumnType("datetime")
          .HasColumnName("fec_modif");
      entity.Property(e => e.Comentario)
          .HasColumnType("text")
          .HasColumnName("comentario");
      entity.Property(e => e.FactDescMin)
          .HasMaxLength(32)
          .HasColumnName("fact_desc_min");
      entity.Property(e => e.FactDescMax)
          .HasMaxLength(32)
          .HasColumnName("fact_desc_max");
      entity.Property(e => e.DescValida)
          .HasMaxLength(16)
          .HasColumnName("desc_valida");
      entity.Property(e => e.FamiliaId)
          .HasColumnName("familia_id");
      entity.Property(e => e.FamiliaNombre)
          .HasMaxLength(255)
          .HasColumnName("familia_nombre");
      entity.Property(e => e.GeneroId)
          .HasColumnName("genero_id");
      entity.Property(e => e.GeneroDescripcion)
          .HasMaxLength(255)
          .HasColumnName("genero_descripcion");
      entity.Property(e => e.StockMinimo)
          .HasColumnName("stock_minimo");
      // The column 'frecuencia_mensual' is not present in the current 'articulos' table.
      // Ignore this property to avoid mapping and query errors.
      entity.Ignore(e => e.FrecuenciaMensual);
      entity.Property(e => e.Fuente)
          .HasMaxLength(64)
          .HasColumnName("fuente");
      entity.Property(e => e.TsCarga)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_carga");
      entity.Property(e => e.ActualizadoEn)
          .ValueGeneratedOnAddOrUpdate()
          .HasColumnType("timestamp(6)")
          .HasColumnName("actualizado_en");
    });

    modelBuilder.Entity<JobHistorial>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("jobs_historial");

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.Detalle)
          .HasColumnType("json")
          .HasColumnName("detalle");
      entity.Property(e => e.Estado)
          .HasColumnType("enum('en_cola','ejecutando','exitoso','fallido')")
          .HasColumnName("estado");
      entity.Property(e => e.FechaFin)
          .HasColumnType("timestamp(6)")
          .HasColumnName("fecha_fin");
      entity.Property(e => e.FechaInicio)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("fecha_inicio");
      entity.Property(e => e.TipoJob)
          .HasColumnType("enum('etl','forecast','backfill','export')")
          .HasColumnName("tipo_job");
    });

    modelBuilder.Entity<Prediccion>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("predicciones");

      entity.HasIndex(e => e.JobId, "fk_pred_job");

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.CantidadPredicha)
          .HasPrecision(18, 2)
          .HasColumnName("cantidad_predicha");
      entity.Property(e => e.FechaPredicha).HasColumnName("fecha_predicha");
      entity.Property(e => e.Horizonte).HasColumnName("horizonte");
      entity.Property(e => e.JobId).HasColumnName("job_id");
      entity.Property(e => e.Modelo)
          .HasMaxLength(64)
          .HasColumnName("modelo");
      entity.Property(e => e.R2).HasColumnName("r2");
      entity.Property(e => e.Rmse).HasColumnName("rmse");
      entity.Property(e => e.Sku)
          .HasMaxLength(120)
          .HasColumnName("sku");
      entity.Property(e => e.TsGeneracion)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_generacion");
      entity.Property(e => e.VersionModelo)
          .HasMaxLength(32)
          .HasColumnName("version_modelo");

      entity.HasOne(d => d.Job).WithMany(p => p.Predicciones)
          .HasForeignKey(d => d.JobId)
          .OnDelete(DeleteBehavior.SetNull)
          .HasConstraintName("fk_pred_job");
    });

    modelBuilder.Entity<Usuario>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("usuarios");

      entity.HasIndex(e => e.Correo, "uq_usuarios_correo").IsUnique();

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.ActualizadoEn)
          .ValueGeneratedOnAddOrUpdate()
          .HasColumnType("timestamp(6)")
          .HasColumnName("actualizado_en");
      entity.Property(e => e.Correo)
          .HasMaxLength(254)
          .HasColumnName("correo");
      entity.Property(e => e.CreadoEn)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("creado_en");
      entity.Property(e => e.HashPassword)
          .HasMaxLength(255)
          .HasColumnName("hash_password");
      entity.Property(e => e.Rol)
          .HasColumnType("enum('administrador','duenoDeEmpresa')")
          .HasColumnName("rol");
    });

    modelBuilder.Entity<StockDiario>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("stock_diario");

      entity.HasIndex(e => new { e.Sku, e.Fecha, e.DepositoId }, "uq_stock_sku_fecha_deposito").IsUnique();

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.Sku)
          .HasMaxLength(120)
          .HasColumnName("sku");
      entity.Property(e => e.Fecha)
          .HasConversion(dateOnlyConverter)
          .HasColumnType("date")
          .HasColumnName("fecha");
      entity.Property(e => e.Cantidad)
          .HasDefaultValueSql("0")
          .HasColumnName("cantidad");
      entity.Property(e => e.DepositoId)
          .HasMaxLength(64)
          .HasColumnName("deposito_id");
      entity.Property(e => e.Fuente)
          .HasMaxLength(64)
          .HasColumnName("fuente");
      entity.Property(e => e.TsCarga)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_carga");
    });

    modelBuilder.Entity<VentasMensuales>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("ventas_mensuales");

      entity.HasIndex(e => new { e.Sku, e.Year, e.Month }, "uq_ventasmens_sku_ym").IsUnique();

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.Sku)
          .HasMaxLength(120)
          .HasColumnName("sku");
      entity.Property(e => e.Year)
          .HasColumnType("smallint unsigned")
          .HasColumnName("year");
      entity.Property(e => e.Month)
          .HasColumnType("tinyint unsigned")
          .HasColumnName("month");
      entity.Property(e => e.VentasCantidad)
          .HasDefaultValueSql("0")
          .HasColumnName("ventas_cantidad");
      entity.Property(e => e.DiasConStock)
          .HasDefaultValueSql("0")
          .HasColumnName("dias_con_stock");
      entity.Property(e => e.Fuente)
          .HasColumnType("enum('ws','calculado')")
          .HasColumnName("fuente");
      entity.Property(e => e.TsCarga)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_carga");
      entity.Property(e => e.ActualizadoEn)
          .ValueGeneratedOnAddOrUpdate()
          .HasColumnType("timestamp(6)")
          .HasColumnName("actualizado_en");
    });

    modelBuilder.Entity<VentaHistorica>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("ventas_historicas");

      entity.HasIndex(e => new { e.Fecha, e.Sku, e.Fuente }, "uq_ventas_fecha_sku_fuente").IsUnique();

            // Ignore properties that are not present in the actual DB table
            entity.Ignore(e => e.Barcode);
            entity.Ignore(e => e.DescripcionArticulo);
            entity.Ignore(e => e.FamiliaId);
            entity.Ignore(e => e.FamiliaNombre);
            entity.Ignore(e => e.FrecuenciaMensual);
            entity.Ignore(e => e.GeneroDescripcion);
            entity.Ignore(e => e.GeneroId);
            entity.Ignore(e => e.StockMinimo);

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.Fecha)
          .HasConversion(dateOnlyConverter)
          .HasColumnType("date")
          .HasColumnName("fecha");
      entity.Property(e => e.Sku)
          .HasMaxLength(128)
          .HasColumnName("sku");
      entity.Property(e => e.Cantidad).HasColumnName("cantidad");
      entity.Property(e => e.Fuente)
          .HasMaxLength(64)
          .HasColumnName("fuente");
      entity.Property(e => e.TsCarga)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_carga");
    });

    modelBuilder.Entity<PlanillaVentasCalculada>(entity =>
    {
      entity.HasKey(e => new { e.Sku, e.Year, e.Month }).HasName("PRIMARY");

      entity.ToTable("planilla_ventas_calculada");

      entity.Property(e => e.Sku)
          .HasMaxLength(128)
          .HasColumnName("sku");
      entity.Property(e => e.Year)
          .HasColumnType("smallint unsigned")
          .HasColumnName("year");
      entity.Property(e => e.Month)
          .HasColumnType("tinyint unsigned")
          .HasColumnName("month");
      entity.Property(e => e.VentasCantidad)
          .HasColumnName("ventas_cantidad");
      entity.Property(e => e.DiasConStock)
          .HasColumnName("dias_con_stock");
      entity.Property(e => e.DiasNaturalesMes)
          .HasColumnName("dias_naturales_mes");
      entity.Property(e => e.RotacionDiariaReal)
          .HasPrecision(10, 4)
          .HasColumnName("rotacion_diaria_real");
      entity.Property(e => e.RotacionDiariaBruta)
          .HasPrecision(10, 4)
          .HasColumnName("rotacion_diaria_bruta");
      entity.Property(e => e.RotacionDiariaDesestacionalizada)
          .HasPrecision(10, 4)
          .HasColumnName("rotacion_diaria_desestacionalizada");
      entity.Property(e => e.EstadoMes)
          .HasColumnType("enum('normal','quiebre_parcial','sin_stock')")
          .HasColumnName("estado_mes");
    });
  }
}
