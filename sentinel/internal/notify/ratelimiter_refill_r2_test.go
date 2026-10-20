package notify

import (
	"testing"
	"time"
)

func TestR2_RateLimiterRefill(t *testing.T) {
	l := NewRateLimiter(100, 1)
	if l == nil {
		t.Fatal("NewRateLimiter returned nil")
	}

	if !l.Allow() {
		t.Fatal("first Allow() = false, want true")
	}
	if l.Allow() {
		t.Fatal("second Allow() = true, want false")
	}

	time.Sleep(120 * time.Millisecond)

	if !l.Allow() {
		t.Fatal("Allow() after refill sleep = false, want true")
	}
	if l.Allow() {
		t.Fatal("immediate Allow() after refilled token = true, want false")
	}

	if got := l.Rejected(); got != 2 {
		t.Fatalf("Rejected() = %d, want 2", got)
	}
}

func TestR2_RateLimiterBurstCap(t *testing.T) {
	l := NewRateLimiter(100000, 2)
	if l == nil {
		t.Fatal("NewRateLimiter returned nil")
	}

	if !l.Allow() {
		t.Fatal("first Allow() = false, want true")
	}
	if !l.Allow() {
		t.Fatal("second Allow() = false, want true")
	}

	time.Sleep(50 * time.Millisecond)

	for i := 0; i < 2; i++ {
		if !l.Allow() {
			t.Fatalf("Allow() call %d after burst refill = false, want true", i+1)
		}
	}

	if l.Allow() {
		t.Fatal("third Allow() after burst refill = true, want false")
	}

	if got := l.Rejected(); got != 1 {
		t.Fatalf("Rejected() = %d, want 1", got)
	}
}
