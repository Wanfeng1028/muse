
package notify

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestDeadLetter_PermanentFailureGoesFailedImmediately(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	q.MaxAttempts = 8

	mid := newMonitor(t, st, "dl-permanent")

	if err := q.EnqueueWebhook(mid, srv.URL, "down", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("process due #1: %v", err)
	}

	rows, err := st.ListDeliveries("", mid, 10)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 row, got %d", len(rows))
	}
	if rows[0].Status != "failed" {
		t.Fatalf("want status failed, got %q", rows[0].Status)
	}
	if rows[0].Attempt != 1 {
		t.Fatalf("want attempt 1, got %d", rows[0].Attempt)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("process due #2: %v", err)
	}

	rows, err = st.ListDeliveries("", mid, 10)
	if err != nil {
		t.Fatalf("list #2: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 row after second process, got %d", len(rows))
	}
	if rows[0].Status != "failed" {
		t.Fatalf("want status failed after second process, got %q", rows[0].Status)
	}
	if rows[0].Attempt != 1 {
		t.Fatalf("want attempt 1 after second process, got %d", rows[0].Attempt)
	}
}

func TestDeadLetter_StatusClassification(t *testing.T) {
	cases := []struct {
		name string
		code int
		want string
	}{
		{"bad_request", http.StatusBadRequest, "failed"},
		{"unauthorized", http.StatusUnauthorized, "failed"},
		{"not_found", http.StatusNotFound, "failed"},
		{"request_timeout", http.StatusRequestTimeout, "retrying"},
		{"too_many_requests", http.StatusTooManyRequests, "retrying"},
		{"internal_server_error", http.StatusInternalServerError, "retrying"},
		{"service_unavailable", http.StatusServiceUnavailable, "retrying"},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tc.code)
			}))
			defer srv.Close()

			q, st := newQueueSender(t)
			q.MaxAttempts = 8

			mid := newMonitor(t, st, "dl-class-"+tc.name)

			if err := q.EnqueueWebhook(mid, srv.URL, "down", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
				t.Fatalf("enqueue: %v", err)
			}
			if err := q.ProcessDue(context.Background()); err != nil {
				t.Fatalf("process due: %v", err)
			}

			rows, err := st.ListDeliveries("", mid, 10)
			if err != nil {
				t.Fatalf("list: %v", err)
			}
			if len(rows) != 1 {
				t.Fatalf("want 1 row, got %d", len(rows))
			}
			row := rows[0]
			if row.Status != tc.want {
				t.Fatalf("code %d: want status %q, got %q", tc.code, tc.want, row.Status)
			}
			if row.Attempt != 1 {
				t.Fatalf("code %d: want attempt 1, got %d", tc.code, row.Attempt)
			}
			if tc.want == "retrying" && !row.NextRetryAt.Valid {
				t.Fatalf("code %d: want NextRetryAt valid", tc.code)
			}
		})
	}
}

func TestDeadLetter_ExhaustionTransitionsToDead(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	q, st := newQueueSender(t)
	q.MaxAttempts = 3
	q.BaseBackoffSec = 1

	mid := newMonitor(t, st, "dl-exhaust")

	if err := q.EnqueueWebhook(mid, srv.URL, "down", "n", "t", "2024-01-01T00:00:00Z", ""); err != nil {
		t.Fatalf("enqueue: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("process due round 1: %v", err)
	}

	rows, err := st.ListDeliveries("", mid, 10)
	if err != nil {
		t.Fatalf("list after round 1: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("want 1 row, got %d", len(rows))
	}
	id := rows[0].ID

	past := time.Now().Add(-1 * time.Hour).Format(time.RFC3339)
	if err := st.MarkDeliveryAttempt(id, past, "x"); err != nil {
		t.Fatalf("mark attempt: %v", err)
	}

	if err := q.ProcessDue(context.Background()); err != nil {
		t.Fatalf("process due round 2: %v", err)
	}

	row, err := st.GetDelivery(id)
	if err != nil {
		t.Fatalf("get delivery: %v", err)
	}
	if row.Status != "dead" {
		t.Fatalf("want status dead, got %q", row.Status)
	}
	if row.Attempt != 3 {
		t.Fatalf("want attempt 3, got %d", row.Attempt)
	}
	if row.LastError == "" {
		t.Fatalf("want non-empty LastError")
	}
}
