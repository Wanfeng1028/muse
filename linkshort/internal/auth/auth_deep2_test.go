package auth

import (
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func init() {
	BcryptCost = bcrypt.MinCost
}

func TestValidPasswordPolicyEmptyDeep2(t *testing.T) {
	err := ValidPasswordPolicy("")
	if err == nil {
		t.Fatalf("ValidPasswordPolicy(\"\") = nil, want error")
	}
	if err.Error() != "密码不能为空" {
		t.Fatalf("ValidPasswordPolicy(\"\") error = %q, want %q", err.Error(), "密码不能为空")
	}
}

func TestValidPasswordPolicy128RunesDeep2(t *testing.T) {
	pw := strings.Repeat("a", MaxPasswordRunes)
	if err := ValidPasswordPolicy(pw); err != nil {
		t.Fatalf("ValidPasswordPolicy(128 runes) = %v, want nil", err)
	}
}

func TestValidPasswordPolicy129RunesDeep2(t *testing.T) {
	pw := strings.Repeat("a", MaxPasswordRunes+1)
	err := ValidPasswordPolicy(pw)
	if err == nil {
		t.Fatalf("ValidPasswordPolicy(129 runes) = nil, want error")
	}
	if err.Error() != "密码过长，最多 128 个字符" {
		t.Fatalf("ValidPasswordPolicy(129 runes) error = %q, want %q", err.Error(), "密码过长，最多 128 个字符")
	}
}

func TestValidPasswordPolicy128ChineseRunesDeep2(t *testing.T) {
	pw := strings.Repeat("中", MaxPasswordRunes)
	if len(pw) != MaxPasswordRunes*3 {
		t.Fatalf("precondition failed: byte length = %d, want %d", len(pw), MaxPasswordRunes*3)
	}
	if err := ValidPasswordPolicy(pw); err != nil {
		t.Fatalf("ValidPasswordPolicy(128 chinese runes) = %v, want nil", err)
	}
}

func TestValidPasswordPolicy129ChineseRunesDeep2(t *testing.T) {
	pw := strings.Repeat("中", MaxPasswordRunes+1)
	if len(pw) != (MaxPasswordRunes+1)*3 {
		t.Fatalf("precondition failed: byte length = %d, want %d", len(pw), (MaxPasswordRunes+1)*3)
	}
	err := ValidPasswordPolicy(pw)
	if err == nil {
		t.Fatalf("ValidPasswordPolicy(129 chinese runes) = nil, want error")
	}
	if err.Error() != "密码过长，最多 128 个字符" {
		t.Fatalf("ValidPasswordPolicy(129 chinese runes) error = %q, want %q", err.Error(), "密码过长，最多 128 个字符")
	}
}

func TestHashPasswordEmptyDeep2(t *testing.T) {
	hash, err := HashPassword("")
	if err == nil {
		t.Fatalf("HashPassword(\"\") error = nil, want error")
	}
	if hash != "" {
		t.Fatalf("HashPassword(\"\") hash = %q, want empty", hash)
	}
}

func TestHashPasswordTooLongDeep2(t *testing.T) {
	pw := strings.Repeat("a", MaxPasswordRunes+1)
	hash, err := HashPassword(pw)
	if err == nil {
		t.Fatalf("HashPassword(129 runes) error = nil, want error")
	}
	if hash != "" {
		t.Fatalf("HashPassword(129 runes) hash = %q, want empty", hash)
	}
}

func TestHashPasswordNormalDeep2(t *testing.T) {
	pw := "correct horse battery staple"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword(%q) error = %v, want nil", pw, err)
	}
	if !strings.HasPrefix(hash, "$2a$") {
		t.Fatalf("HashPassword(%q) = %q, want prefix %q", pw, hash, "$2a$")
	}
	if hash == pw {
		t.Fatalf("HashPassword(%q) returned plaintext, want hashed value", pw)
	}
}

func TestCheckPasswordEmptyHashDeep2(t *testing.T) {
	ok := CheckPassword("", "whatever")
	if ok {
		t.Fatalf("CheckPassword(\"\", pw) = true, want false")
	}
}

func TestCheckPasswordCorrectDeep2(t *testing.T) {
	pw := "s3cr3t-p@ssw0rd"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword(%q) error = %v, want nil", pw, err)
	}
	if !CheckPassword(hash, pw) {
		t.Fatalf("CheckPassword(hash, %q) = false, want true", pw)
	}
}

func TestCheckPasswordWrongDeep2(t *testing.T) {
	pw := "s3cr3t-p@ssw0rd"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword(%q) error = %v, want nil", pw, err)
	}
	if CheckPassword(hash, "wrong-password") {
		t.Fatalf("CheckPassword(hash, wrong) = true, want false")
	}
}

func TestCheckPasswordInvalidHashDeep2(t *testing.T) {
	ok := CheckPassword("not-a-bcrypt-hash", "any")
	if ok {
		t.Fatalf("CheckPassword(invalid hash, pw) = true, want false")
	}
}

func TestHashPasswordSaltRandomDeep2(t *testing.T) {
	pw := "same-password-twice"
	h1, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword #1(%q) error = %v, want nil", pw, err)
	}
	h2, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword #2(%q) error = %v, want nil", pw, err)
	}
	if h1 == h2 {
		t.Fatalf("two hashes of same password are identical (%q), want distinct salts", h1)
	}
	if !CheckPassword(h1, pw) {
		t.Fatalf("CheckPassword(h1, %q) = false, want true", pw)
	}
	if !CheckPassword(h2, pw) {
		t.Fatalf("CheckPassword(h2, %q) = false, want true", pw)
	}
}