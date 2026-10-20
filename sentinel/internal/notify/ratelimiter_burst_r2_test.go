package notify

import "testing"

func TestR2_RateLimiterDisabled(t *testing.T) {
	if got := NewRateLimiter(0, 10); got != nil {
		t.Fatalf("NewRateLimiter(0, 10) = %v, want nil", got)
	}
	if got := NewRateLimiter(5, 0); got != nil {
		t.Fatalf("NewRateLimiter(5, 0) = %v, want nil", got)
	}
	if got := NewRateLimiter(-1, 5); got != nil {
		t.Fatalf("NewRateLimiter(-1, 5) = %v, want nil", got)
	}
}

func TestR2_RateLimiterBurstExact(t *testing.T) {
	l := NewRateLimiter(0.001, 3)
	if l == nil {
		t.Fatal("NewRateLimiter(0.001, 3) = nil, want non-nil limiter")
	}

	for i := 0; i < 3; i++ {
		if !l.Allow() {
			t.Fatalf("Allow() call %d = false, want true", i+1)
		}
	}
	if got := l.Rejected(); got != 0 {
		t.Fatalf("Rejected() after successful burst = %d, want 0", got)
	}

	for i := 0; i < 2; i++ {
		if l.Allow() {
			t.Fatalf("Allow() call after burst %d = true, want false", i+1)
		}
	}
	if got := l.Rejected(); got != 2 {
		t.Fatalf("Rejected() = %d, want 2", got)
	}
}

func TestR2_RateLimiterRejectedStartsZero(t *testing.T) {
	l := NewRateLimiter(0.001, 3)
	if l == nil {
		t.Fatal("NewRateLimiter(0.001, 3) = nil, want non-nil limiter")
	}

	if got := l.Rejected(); got != 0 {
		t.Fatalf("Rejected() immediately after construction = %d, want 0", got)
	}
	if !l.Allow() {
		t.Fatal("Allow() = false, want true")
	}
	if got := l.Rejected(); got != 0 {
		t.Fatalf("Rejected() after one successful Allow() = %d, want 0", got)
	}
}
