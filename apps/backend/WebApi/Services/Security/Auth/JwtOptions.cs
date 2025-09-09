namespace Services.Security.Auth
{
  public class JwtOptions
  {
    public string Issuer { get; set; } = "evalutia";
    public string Audience { get; set; } = "evalutia.web";
    public string Secret { get; set; } = null!;
    public int ExpiresHours { get; set; } = 12;
  }
}
