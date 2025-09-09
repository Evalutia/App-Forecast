using WebApi.Data;
using WebApi.Models;

namespace DataAccess.Repositories.UsuarioDataAccess
{
  public class UsuarioRepository : IUsuarioRepository
  {
    private readonly EvalutiaDbContext _db;
    public UsuarioRepository(EvalutiaDbContext db) { _db = db; }

    public Usuario? GetById(int id)
    {
      return _db.Usuarios.FirstOrDefault(u => (int)u.Id == id);
    }

    public Usuario? GetByCorreo(string correo)
    {
      return _db.Usuarios.FirstOrDefault(u => u.Correo == correo);
    }

    public (IReadOnlyList<Usuario> Items, int Total) List(int page, int pageSize, string? correo, string? rol)
    {
      var q = _db.Usuarios.AsQueryable();
      if (!string.IsNullOrWhiteSpace(correo)) q = q.Where(u => u.Correo!.Contains(correo));
      if (!string.IsNullOrWhiteSpace(rol)) q = q.Where(u => u.Rol == rol);

      var total = q.Count();
      var items = q.OrderBy(u => u.Id)
                   .Skip((page - 1) * pageSize)
                   .Take(pageSize)
                   .ToList();
      return (items, total);
    }

    public bool CorreoExists(string correo)
    {
      return _db.Usuarios.Any(u => u.Correo == correo);
    }

    public int Create(Usuario u)
    {
      _db.Usuarios.Add(u);
      _db.SaveChanges();
      return (int)u.Id;
    }

    public void Update(Usuario u)
    {
      _db.Usuarios.Update(u);
      _db.SaveChanges();
    }

    public bool DeleteById(int id)
    {
      var u = _db.Usuarios.FirstOrDefault(x => (int)x.Id == id);
      if (u is null) return false;
      _db.Usuarios.Remove(u);
      _db.SaveChanges();
      return true;
    }
  }
}
