package auth

import (
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func TestValidPasswordPolicy(t *testing.T) {
	if err := ValidPasswordPolicy(""); err == nil {
		t.Fatalf("expected error for empty password")
	}
	if err := ValidPasswordPolicy(strings.Repeat("a", 128)); err != nil {
		t.Fatalf("expected 128 runes to pass, got %v", err)
	}
	if err := ValidPasswordPolicy(strings.Repeat("a", 129)); err == nil {
		t.Fatalf("expected error for 129 runes")
	}
	if err := ValidPasswordPolicy(strings.Repeat("中", 64)); err != nil {
		t.Fatalf("expected 64 chinese runes to pass, got %v", err)
	}
}

func TestHashAndCheckPassword(t *testing.T) {
	BcryptCost = bcrypt.MinCost
	defer func() { BcryptCost = bcrypt.DefaultCost }()

	hash, err := HashPassword("correct-horse")
	if err != nil {
		t.Fatalf("HashPassword failed: %v", err)
	}
	if !strings.HasPrefix(hash, "$2a$") {
		t.Fatalf("hash should start with $2a$, got %q", hash)
	}
	if hash == "correct-horse" {
		t.Fatalf("hash must not equal plaintext")
	}
	if !CheckPassword(hash, "correct-horse") {
		t.Fatalf("expected CheckPassword true for correct password")
	}
	if CheckPassword(hash, "wrong") {
		t.Fatalf("expected CheckPassword false for wrong password")
	}
	if CheckPassword("", "x") {
		t.Fatalf("expected CheckPassword false for empty hash")
	}
	if _, err := HashPassword(""); err == nil {
		t.Fatalf("expected HashPassword error for empty password")
	}
}

func TestBcryptCostVariable(t *testing.T) {
	if BcryptCost != bcrypt.DefaultCost {
		t.Fatalf("BcryptCost should default to bcrypt.DefaultCost, got %d", BcryptCost)
	}
}
