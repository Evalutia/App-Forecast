namespace WebApi.Controllers.Jobs.DTOs
{
  public class JobsQueryDto
  {
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 50;
    public string? Tipo { get; init; }      
    public string? Estado { get; init; }    
    public DateTime? Desde { get; init; }   
    public DateTime? Hasta { get; init; }   
  }

  public class JobItemOutDto
  {
    public ulong Id { get; init; }
    public string TipoJob { get; init; } = "";
    public string Estado { get; init; } = "";
    public DateTime FechaInicio { get; init; }
    public DateTime? FechaFin { get; init; }
  }

  public class JobDetailOutDto : JobItemOutDto
  {
    public string? Detalle { get; init; }   
  }

  public class PrediccionOutDto
  {
    public long Id { get; init; }
    public string Sku { get; init; } = "";
    public DateTime FechaPredicha { get; init; }
    public decimal CantidadPredicha { get; init; }
    public string Modelo { get; init; } = "";
    public int Horizonte { get; init; }
    public decimal? Rmse { get; init; }
    public decimal? R2 { get; init; }
  }

  public class PagedResultDto<T>
  {
    public IEnumerable<T> Items { get; init; } = Enumerable.Empty<T>();
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int Total { get; init; }
    public PagedResultDto(IEnumerable<T> items, int page, int pageSize, int total)
    {
      Items = items; Page = page; PageSize = pageSize; Total = total;
    }
  }

}
