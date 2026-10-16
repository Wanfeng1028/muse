using System.Security.Cryptography;
using System.Text;

namespace VoxLoom.Core.Backup;

internal static class BackupCrypto
{
    private static readonly byte[] Magic = Encoding.ASCII.GetBytes("VXENC1");
    private const int SaltSize = 16;
    private const int NonceSize = 12;
    private const int TagSize = 16;
    private const int KeySize = 32;
    private const int Iterations = 200_000;

    public static bool IsEncryptedFile(string path)
    {
        using var stream = File.OpenRead(path);
        var header = new byte[Magic.Length];
        var read = stream.Read(header, 0, header.Length);
        if (read != header.Length) return false;
        for (int i = 0; i < header.Length; i++)
        {
            if (header[i] != Magic[i]) return false;
        }
        return true;
    }

    public static void EncryptFile(string inputZipPath, string password)
    {
        var salt = RandomNumberGenerator.GetBytes(SaltSize);
        var nonce = RandomNumberGenerator.GetBytes(NonceSize);
        var key = DeriveKey(password, salt);

        var plaintext = File.ReadAllBytes(inputZipPath);
        var ciphertext = new byte[plaintext.Length];
        var tag = new byte[TagSize];

        using (var aes = new AesGcm(key, AesGcm.TagByteSizes.MaxSize))
        {
            aes.Encrypt(nonce, plaintext, ciphertext, tag);
        }

        using var output = File.Create(inputZipPath);
        output.Write(Magic, 0, Magic.Length);
        output.Write(salt, 0, salt.Length);
        output.Write(nonce, 0, nonce.Length);
        output.Write(tag, 0, tag.Length);
        output.Write(ciphertext, 0, ciphertext.Length);
    }

    public static string DecryptToTempFile(string encryptedPath, string password)
    {
        var data = File.ReadAllBytes(encryptedPath);
        var headerLen = Magic.Length + SaltSize + NonceSize + TagSize;
        if (data.Length < headerLen)
            throw new BackupException("备份密码错误，无法解密");

        var salt = new byte[SaltSize];
        var nonce = new byte[NonceSize];
        var tag = new byte[TagSize];
        var ciphertext = new byte[data.Length - headerLen];

        Buffer.BlockCopy(data, Magic.Length, salt, 0, SaltSize);
        Buffer.BlockCopy(data, Magic.Length + SaltSize, nonce, 0, NonceSize);
        Buffer.BlockCopy(data, Magic.Length + SaltSize + NonceSize, tag, 0, TagSize);
        Buffer.BlockCopy(data, headerLen, ciphertext, 0, ciphertext.Length);

        var key = DeriveKey(password, salt);
        var plaintext = new byte[ciphertext.Length];

        try
        {
            using var aes = new AesGcm(key, AesGcm.TagByteSizes.MaxSize);
            aes.Decrypt(nonce, ciphertext, tag, plaintext);
        }
        catch (CryptographicException ex)
        {
            throw new BackupException("备份密码错误，无法解密", ex);
        }

        var temp = Path.Combine(Path.GetTempPath(), "voxloom-dec-" + Guid.NewGuid().ToString("N")[..8] + ".zip");
        File.WriteAllBytes(temp, plaintext);
        return temp;
    }

    private static byte[] DeriveKey(string password, byte[] salt)
    {
        var passwordBytes = Encoding.UTF8.GetBytes(password);
        using var kdf = new Rfc2898DeriveBytes(passwordBytes, salt, Iterations, HashAlgorithmName.SHA256);
        return kdf.GetBytes(KeySize);
    }
}
