namespace Services.Security
{
  public static class PasswordHasher
  {
    public static string Hash(string password) => BCrypt.Net.BCrypt.HashPassword(password, workFactor: 11);
    public static bool Verify(string password, string hash) => BCrypt.Net.BCrypt.Verify(password, hash);
  }
}
