
package store

import (
	"database/sql"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestMarkDeliveryDead_ConcurrentOneWins(t *testing.T) {
	s := openTestStore(t)
	mid, err := s.CreateMonitor(Monitor{
		Name: "dl", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if _, err := s.EnqueueDelivery(mid, "http://example.invalid/hook", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	future := time.Now().Add(1 * time.Hour).Format(time.RFC3339)
	claimed, err := s.ClaimDueDeliveries(future, 10)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if len(claimed) != 1 {
		t.Fatalf("want 1 claimed, got %d", len(claimed))
	}
	id := claimed[0].ID

	var (
		wg      sync.WaitGroup
		mu      sync.Mutex
		nilErrs int
		noRows  int
		other   []error
	)

	wg.Add(2)
	for i := 0; i < 2; i++ {
		go func() {
			defer wg.Done()
			err := s.MarkDeliveryDead(id, "x")
			mu.Lock()
			defer mu.Unlock()
			switch {
			case err == nil:
				nilErrs++
			case errors.Is(err, sql.ErrNoRows):
				noRows++
			default:
				other = append(other, err)
			}
		}()
	}
	wg.Wait()

	if len(other) != 0 {
		t.Errorf("unexpected errors: %v", other)
	}
	if nilErrs != 1 {
		t.Errorf("want exactly 1 nil error, got %d", nilErrs)
	}
	if noRows != 1 {
		t.Errorf("want exactly 1 sql.ErrNoRows, got %d", noRows)
	}

	row, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("get delivery: %v", err)
	}
	if row.Status != "dead" {
		t.Errorf("want status dead, got %q", row.Status)
	}
	if row.Attempt != 1 {
		t.Errorf("want attempt 1, got %d", row.Attempt)
	}
}

func TestMarkDeliveryDead_RequiresDelivering(t *testing.T) {
	s := openTestStore(t)
	mid, err := s.CreateMonitor(Monitor{
		Name: "dl", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if _, err := s.EnqueueDelivery(mid, "http://example.invalid/hook", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	rows, err := s.ListDeliveries("", mid, 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 row, got %d", len(rows))
	}
	id := rows[0].ID

	err = s.MarkDeliveryDead(id, "x")
	if !errors.Is(err, sql.ErrNoRows) {
		t.Fatalf("want sql.ErrNoRows, got %v", err)
	}

	row, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("get delivery: %v", err)
	}
	if row.Status != "pending" {
		t.Fatalf("want status pending, got %q", row.Status)
	}
}

func TestRetryDelivery_AllowsDead(t *testing.T) {
	s := openTestStore(t)
	mid, err := s.CreateMonitor(Monitor{
		Name: "dl", Kind: "http", Target: "https://example.com",
		Method: "GET", ExpectedStatus: 200, TimeoutSec: 5,
		IntervalSec: 60, Enabled: 1, TenantID: 1,
	})
	if err != nil {
		t.Fatalf("CreateMonitor: %v", err)
	}

	if _, err := s.EnqueueDelivery(mid, "http://example.invalid/hook", "down", `{}`, 8); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	future := time.Now().Add(1 * time.Hour).Format(time.RFC3339)
	claimed, err := s.ClaimDueDeliveries(future, 10)
	if err != nil {
		t.Fatalf("claim: %v", err)
	}
	if len(claimed) != 1 {
		t.Fatalf("want 1 claimed, got %d", len(claimed))
	}
	id := claimed[0].ID

	if err := s.MarkDeliveryDead(id, "x"); err != nil {
		t.Fatalf("mark dead: %v", err)
	}

	if err := s.RetryDelivery(id); err != nil {
		t.Fatalf("retry delivery: %v", err)
	}

	row, err := s.GetDelivery(id)
	if err != nil {
		t.Fatalf("get delivery: %v", err)
	}
	if row.Status != "pending" {
		t.Fatalf("want status pending, got %q", row.Status)
	}
	if row.Attempt != 0 {
		t.Fatalf("want attempt 0, got %d", row.Attempt)
	}
	if row.LastError != "" {
		t.Fatalf("want empty LastError, got %q", row.LastError)
	}
}
