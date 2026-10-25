package api

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

type overdueItem struct {
	ID          int64    `json:"id"`
	Title       string   `json:"title"`
	DueDate     string   `json:"dueDate"`
	OverdueDays int      `json:"overdueDays"`
	Tags        []string `json:"tags"`
	Hard        bool     `json:"hard"`
}

func seedOverdueReview(t *testing.T, st *store.Store, title string, reviewDay time.Time, user string) {
	t.Helper()
	note, err := st.CreateNote(store.Note{Title: title, Body: "body-" + title})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	if _, err := st.RecordReview(context.Background(), note.ID, 5, reviewDay, user); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}
}

func TestReviewOverdue_EmptyDB(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/overdue", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}
	var got []overdueItem
	decodeReviewJSON(t, resp, &got)
	if len(got) != 0 {
		t.Errorf("expected 0 items, got %d", len(got))
	}
}

func TestReviewOverdue_FilterOrderAndUser(t *testing.T) {
	srv, st := newReviewTestServer(t)
	now := time.Now()
	// grade 5 first review: interval 1 day, so due = reviewDay + 1 day.
	seedOverdueReview(t, st, "overdue-10", now.AddDate(0, 0, -11), store.DefaultUser)
	seedOverdueReview(t, st, "overdue-1", now.AddDate(0, 0, -2), store.DefaultUser)
	seedOverdueReview(t, st, "due-today", now.AddDate(0, 0, -1), store.DefaultUser)
	seedOverdueReview(t, st, "future", now, store.DefaultUser)
	seedOverdueReview(t, st, "other-overdue", now.AddDate(0, 0, -6), "other-user")

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/overdue", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}
	var got []overdueItem
	decodeReviewJSON(t, resp, &got)
	if len(got) != 2 {
		t.Fatalf("expected 2 overdue items, got %d", len(got))
	}
	if got[0].Title != "overdue-10" || got[0].OverdueDays != 10 {
		t.Errorf("got[0] = %q overdueDays %d, want overdue-10 10", got[0].Title, got[0].OverdueDays)
	}
	if got[1].Title != "overdue-1" || got[1].OverdueDays != 1 {
		t.Errorf("got[1] = %q overdueDays %d, want overdue-1 1", got[1].Title, got[1].OverdueDays)
	}
	if got[0].Tags == nil {
		t.Errorf("expected non-nil Tags")
	}

	respB := doReviewJSONUser(t, http.MethodGet, srv.URL+"/api/review/overdue", nil, "other-user")
	defer respB.Body.Close()
	var gotB []overdueItem
	decodeReviewJSON(t, respB, &gotB)
	if len(gotB) != 1 || gotB[0].Title != "other-overdue" {
		t.Errorf("other-user: got %d items, want 1 other-overdue", len(gotB))
	}
}

func TestReviewOverdue_LimitAndMethod(t *testing.T) {
	srv, st := newReviewTestServer(t)
	now := time.Now()
	seedOverdueReview(t, st, "o1", now.AddDate(0, 0, -3), store.DefaultUser)
	seedOverdueReview(t, st, "o2", now.AddDate(0, 0, -4), store.DefaultUser)

	for _, q := range []string{"limit=1", "limit=0", "limit=999", "limit=abc"} {
		resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/overdue?"+q, nil)
		var got []overdueItem
		decodeReviewJSON(t, resp, &got)
		want := 2
		if q == "limit=1" {
			want = 1
		}
		if resp.StatusCode != http.StatusOK || len(got) != want {
			t.Errorf("query %s: status %d, items %d, want 200 / %d", q, resp.StatusCode, len(got), want)
		}
	}

	resp := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/overdue", nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("POST: status %d, want 405", resp.StatusCode)
	}
}
