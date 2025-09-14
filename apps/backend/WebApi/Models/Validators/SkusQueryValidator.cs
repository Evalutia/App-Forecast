namespace Models.Validators
{
  public static class SkusQueryValidator
  {
    public static void Validar(string? filtro)
    {
      if (!string.IsNullOrEmpty(filtro) && filtro.Length < 2)
      {
        throw new InvalidOperationException("El filtro de SKU es demasiado corto");
      }
    }
  }
}
