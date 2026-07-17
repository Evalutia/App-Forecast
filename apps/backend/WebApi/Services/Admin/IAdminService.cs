using System;

namespace Services.Admin
{
  public interface IAdminService
  {
    RecalcResult Recalc(string? sku, DateOnly? fromDate, DateOnly? toDate);
  }
}
