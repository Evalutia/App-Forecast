using System.ComponentModel.DataAnnotations;

namespace WebApi.Models;

public class RecalcRequest
{
  public string? Sku { get; set; }

  [RegularExpression(@"^\d{4}-\d{2}-\d{2}$", ErrorMessage = "fromDate must be YYYY-MM-DD")]
  public string? FromDate { get; set; }

  [RegularExpression(@"^\d{4}-\d{2}-\d{2}$", ErrorMessage = "toDate must be YYYY-MM-DD")]
  public string? ToDate { get; set; }
}
