namespace Models.Validators
{
  public static class SkusQueryValidator
  {
    public static void ValidarFiltro(string? filtro)
    {
      if (!string.IsNullOrEmpty(filtro) && filtro.Length < 1)
      {
        throw new InvalidOperationException("El filtro debe tener al menos 1 caracteres");
      }

      if (!string.IsNullOrEmpty(filtro) && filtro.Length > 50)
      {
        throw new InvalidOperationException("El filtro no puede superar los 50 caracteres");
      }
    }
  }
}
