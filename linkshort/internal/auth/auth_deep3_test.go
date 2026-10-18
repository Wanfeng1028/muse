package auth

import (
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func TestValidPasswordPolicyExactlyOneRuneDeep3(t *testing.T) {
	if err := ValidPasswordPolicy("x"); err != nil {
		t.Fatalf("ValidPasswordPolicy(\"x\") = %v, want nil", err)
	}
}

func TestValidPasswordPolicySingleChineseRuneDeep3(t *testing.T) {
	if err := ValidPasswordPolicy("中"); err != nil {
		t.Fatalf("ValidPasswordPolicy(\"中\") = %v, want nil", err)
	}
}

func TestValidPasswordPolicyWhitespaceOnlyDeep3(t *testing.T) {
	if err := ValidPasswordPolicy("   "); err != nil {
		t.Fatalf("ValidPasswordPolicy(spaces) = %v, want nil", err)
	}
}

func TestValidPasswordPolicyEmoji128RunesDeep3(t *testing.T) {
	pw := strings.Repeat("\U0001F600", MaxPasswordRunes)
	if len([]rune(pw)) != MaxPasswordRunes {
		t.Fatalf("precondition failed: rune length = %d, want %d", len([]rune(pw)), MaxPasswordRunes)
	}
	if err := ValidPasswordPolicy(pw); err != nil {
		t.Fatalf("ValidPasswordPolicy(128 emoji runes) = %v, want nil", err)
	}
}

func TestValidPasswordPolicyEmoji129RunesDeep3(t *testing.T) {
	pw := strings.Repeat("\U0001F600", MaxPasswordRunes+1)
	err := ValidPasswordPolicy(pw)
	if err == nil {
		t.Fatalf("ValidPasswordPolicy(129 emoji runes) = nil, want error")
	}
	if err.Error() != "密码过长，最多 128 个字符" {
		t.Fatalf("ValidPasswordPolicy(129 emoji runes) error = %q, want %q", err.Error(), "密码过长，最多 128 个字符")
	}
}

func TestHashPasswordExactly128RunesDeep3(t *testing.T) {
	pw := strings.Repeat("z", MaxPasswordRunes)
	hash, err := HashPassword(pw)
	if err == nil {
		t.Fatalf("HashPassword(128 runes) error = nil, want error")
	}
	if hash != "" {
		t.Fatalf("HashPassword(128 runes) hash = %q, want empty", hash)
	}
	if !strings.Contains(err.Error(), "hash password") {
		t.Fatalf("HashPassword(128 runes) error = %q, want it to contain %q", err.Error(), "hash password")
	}
}

func TestHashPasswordExactly129RunesDeep3(t *testing.T) {
	pw := strings.Repeat("z", MaxPasswordRunes+1)
	hash, err := HashPassword(pw)
	if err == nil {
		t.Fatalf("HashPassword(129 runes) error = nil, want error")
	}
	if hash != "" {
		t.Fatalf("HashPassword(129 runes) hash = %q, want empty", hash)
	}
}

func TestHashPasswordInvalidBcryptCostDeep3(t *testing.T) {
	orig := BcryptCost
	BcryptCost = bcrypt.MinCost - 1
	defer func() { BcryptCost = orig }()

	hash, err := HashPassword("valid-password")
	if err != nil {
		t.Fatalf("HashPassword with low cost error = %v, want nil", err)
	}
	if hash == "" {
		t.Fatalf("HashPassword with low cost hash = \"\", want non-empty")
	}
	if !CheckPassword(hash, "valid-password") {
		t.Fatalf("CheckPassword(hash, %q) = false, want true", "valid-password")
	}
}

func TestHashPasswordCostAboveMaxDeep3(t *testing.T) {
	orig := BcryptCost
	BcryptCost = bcrypt.MaxCost + 1
	defer func() { BcryptCost = orig }()

	hash, err := HashPassword("valid-password")
	if err == nil {
		t.Fatalf("HashPassword with cost > MaxCost error = nil, want error")
	}
	if hash != "" {
		t.Fatalf("HashPassword with cost > MaxCost hash = %q, want empty", hash)
	}
}

func TestHashPasswordPolicyErrorPreservedDeep3(t *testing.T) {
	hash, err := HashPassword("")
	if err == nil {
		t.Fatalf("HashPassword(\"\") error = nil, want policy error")
	}
	if err.Error() != "密码不能为空" {
		t.Fatalf("HashPassword(\"\") error = %q, want %q", err.Error(), "密码不能为空")
	}
	if hash != "" {
		t.Fatalf("HashPassword(\"\") hash = %q, want empty", hash)
	}
}

func TestCheckPasswordHashIsPlaintextDeep3(t *testing.T) {
	pw := "plaintext-as-hash"
	if CheckPassword(pw, pw) {
		t.Fatalf("CheckPassword(plaintext, plaintext) = true, want false")
	}
}

func TestCheckPasswordEmptyBothDeep3(t *testing.T) {
	if CheckPassword("", "") {
		t.Fatalf("CheckPassword(\"\", \"\") = true, want false")
	}
}

func TestCheckPasswordEmptyPasswordNonEmptyHashDeep3(t *testing.T) {
	hash, err := HashPassword("real-password")
	if err != nil {
		t.Fatalf("HashPassword error = %v, want nil", err)
	}
	if CheckPassword(hash, "") {
		t.Fatalf("CheckPassword(hash, \"\") = true, want false")
	}
}

func TestCheckPasswordTruncatedHashDeep3(t *testing.T) {
	hash, err := HashPassword("some-password")
	if err != nil {
		t.Fatalf("HashPassword error = %v, want nil", err)
	}
	truncated := hash[:len(hash)-5]
	if CheckPassword(truncated, "some-password") {
		t.Fatalf("CheckPassword(truncated hash, pw) = true, want false")
	}
}

func TestCheckPasswordModifiedHashDeep3(t *testing.T) {
	hash, err := HashPassword("some-password")
	if err != nil {
		t.Fatalf("HashPassword error = %v, want nil", err)
	}
	b := []byte(hash)
	b[len(b)-1] ^= 0x01
	modified := string(b)
	if modified == hash {
		t.Fatalf("precondition failed: modified hash equals original")
	}
	if CheckPassword(modified, "some-password") {
		t.Fatalf("CheckPassword(modified hash, pw) = true, want false")
	}
}

func TestCheckPasswordUnicodePasswordDeep3(t *testing.T) {
	pw := "密码-🔐-pass"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword(unicode pw) error = %v, want nil", err)
	}
	if !CheckPassword(hash, pw) {
		t.Fatalf("CheckPassword(hash, unicode pw) = false, want true")
	}
	if CheckPassword(hash, "密码-🔐-pass!") {
		t.Fatalf("CheckPassword(hash, near-miss unicode pw) = true, want false")
	}
}

func TestCheckPasswordByteLevelNearMissDeep3(t *testing.T) {
	pw := "abc"
	hash, err := HashPassword(pw)
	if err != nil {
		t.Fatalf("HashPassword(%q) error = %v, want nil", pw, err)
	}
	if CheckPassword(hash, "abcd") {
		t.Fatalf("CheckPassword(hash, %q) = true, want false", "abcd")
	}
	if CheckPassword(hash, "ab") {
		t.Fatalf("CheckPassword(hash, %q) = true, want false", "ab")
	}
}

func TestCheckPasswordNonBcryptVersionPrefixDeep3(t *testing.T) {
	hash, err := HashPassword("payload")
	if err != nil {
		t.Fatalf("HashPassword error = %v, want nil", err)
	}
	if !strings.HasPrefix(hash, "$2") {
		t.Fatalf("precondition failed: hash = %q, want bcrypt prefix", hash)
	}
	mutated := "$9" + hash[2:]
	if CheckPassword(mutated, "payload") {
		t.Fatalf("CheckPassword(unknown bcrypt version, pw) = true, want false")
	}
}

func TestHashPasswordDeterministicAcrossRepeatsDeep3(t *testing.T) {
	pw := "repeat-check"
	var hashes []string
	for i := 0; i < 4; i++ {
		h, err := HashPassword(pw)
		if err != nil {
			t.Fatalf("HashPassword iteration %d error = %v, want nil", i, err)
		}
		hashes = append(hashes, h)
	}
	seen := make(map[string]bool, len(hashes))
	for _, h := range hashes {
		if seen[h] {
			t.Fatalf("duplicate hash %q across %d iterations, want all distinct", h, len(hashes))
		}
		seen[h] = true
		if !CheckPassword(h, pw) {
			t.Fatalf("CheckPassword(%q, %q) = false, want true", h, pw)
		}
	}
}
