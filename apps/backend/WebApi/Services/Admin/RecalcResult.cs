using System.Collections.Generic;

namespace Services.Admin
{
  public class RecalcResult
  {
    public int MonthsRecalculated { get; set; }
    public List<string> Errors { get; set; } = new();
  }
}
