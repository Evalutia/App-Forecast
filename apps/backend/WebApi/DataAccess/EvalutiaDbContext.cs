using Microsoft.EntityFrameworkCore;
using Pomelo.EntityFrameworkCore.MySql.Scaffolding.Internal;
using System;
using System.Collections.Generic;
using System.Reflection.Emit;
using WebApi.Models;

namespace WebApi.Data;

public partial class EvalutiaDbContext : DbContext
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

  public virtual DbSet<VentaHistorica> VentasHistoricas { get; set; }

  protected override void OnModelCreating(ModelBuilder modelBuilder)
  {
    modelBuilder
        .UseCollation("utf8mb4_0900_ai_ci")
        .HasCharSet("utf8mb4");

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

    modelBuilder.Entity<VentaHistorica>(entity =>
    {
      entity.HasKey(e => e.Id).HasName("PRIMARY");

      entity.ToTable("ventas_historicas");

      entity.HasIndex(e => new { e.Fecha, e.Sku, e.Fuente }, "uq_ventas_fecha_sku_fuente").IsUnique();

      entity.Property(e => e.Id).HasColumnName("id");
      entity.Property(e => e.Cantidad).HasColumnName("cantidad");
      entity.Property(e => e.Fecha).HasColumnName("fecha");
      entity.Property(e => e.Fuente)
          .HasMaxLength(64)
          .HasColumnName("fuente");
      entity.Property(e => e.Sku)
          .HasMaxLength(120)
          .HasColumnName("sku");
      entity.Property(e => e.TsCarga)
          .HasDefaultValueSql("CURRENT_TIMESTAMP(6)")
          .HasColumnType("timestamp(6)")
          .HasColumnName("ts_carga");
    });

    OnModelCreatingPartial(modelBuilder);
  }

  partial void OnModelCreatingPartial(ModelBuilder modelBuilder);
}
