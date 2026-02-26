using System.Collections.Generic;
using WebApi.Models;

namespace DataAccess.Repositories.ArticuloDataAccess
{
  public interface IArticuloRepository
  {
    Articulo? FindBySku(string sku);
    Articulo Upsert(Articulo articulo);
    IEnumerable<Articulo> FindByFamilyOrGenre(int? familyId, int? genreId, int page, int pageSize);
  }
}
