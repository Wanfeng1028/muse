package push

import (
	"math/rand"
	"testing"
	"time"
)

func TestBackoffForAttempt_NegativeAttempt(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: 1000 * time.Millisecond,
		MaxBackoff:  30 * time.Second,
		JitterRatio: 0,
	}
	got := backoffForAttempt(policy, -5, nil)
	want := 1000 * time.Millisecond
	if got != want {
		t.Fatalf("negative attempt: got %v, want %v", got, want)
	}
}

func TestBackoffForAttempt_ZeroBase(t *testing.T) {
	policy := RetryPolicy{
		MaxRetries:  3,
		BaseBackoff: 0,
		MaxBackoff:  30 * time.Second,
		JitterRatio: 0.25,
	}
	rng := rand.New(rand.NewSource(1))
	got := backoffForAttempt(policy, 5, rng)
	if got != 0 {
		t.Fatalf("zero base: got %v, want 0", got)
	}
}
