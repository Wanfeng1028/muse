package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newReviewTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	mux := http.NewServeMux()
	RegisterReviewRoutes(mux, st)
	srv := httptest.NewServer(mux)
	t.Cleanup(func() {
		srv.Close()
	})
	return srv, st
}

func doReviewJSON(t *testing.T, method, url string, body any) *http.Response {
	t.Helper()
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, url, rdr)
	if err != nil {
		t.Fatalf("NewRequest: %v", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("Do: %v", err)
	}
	return resp
}

func decodeReviewJSON(t *testing.T, resp *http.Response, v any) {
	t.Helper()
	defer resp.Body.Close()
	if err := json.NewDecoder(resp.Body).Decode(v); err != nil {
		t.Fatalf("decode response: %v", err)
	}
}

func TestReviewGradeInterval(t *testing.T) {
	srv, st := newReviewTestServer(t)

	note, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	noteID := strconv.FormatInt(note.ID, 10)

	resp := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/"+noteID, map[string]any{"grade": 5})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("first POST status = %d, want 200", resp.StatusCode)
	}
	var first struct {
		EF            float64 `json:"ef"`
		IntervalDays  int     `json:"intervalDays"`
		Repetitions   int     `json:"repetitions"`
		DueDate       string  `json:"dueDate"`
		ReviewedCount int     `json:"reviewedCount"`
	}
	decodeReviewJSON(t, resp, &first)
	if first.IntervalDays != 1 {
		t.Fatalf("first intervalDays = %d, want 1", first.IntervalDays)
	}

	resp2 := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/"+noteID, map[string]any{"grade": 5})
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("second POST status = %d, want 200", resp2.StatusCode)
	}
	var second struct {
		EF            float64 `json:"ef"`
		IntervalDays  int     `json:"intervalDays"`
		Repetitions   int     `json:"repetitions"`
		DueDate       string  `json:"dueDate"`
		ReviewedCount int     `json:"reviewedCount"`
	}
	decodeReviewJSON(t, resp2, &second)
	if second.IntervalDays != 6 {
		t.Fatalf("second intervalDays = %d, want 6", second.IntervalDays)
	}
}

func TestReviewGradeErrors(t *testing.T) {
	srv, st := newReviewTestServer(t)

	note, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	noteID := strconv.FormatInt(note.ID, 10)

	resp := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/"+noteID, nil)
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("empty body status = %d, want 400", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/"+noteID, map[string]any{"grade": 99})
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("grade 99 status = %d, want 400", resp.StatusCode)
	}
	resp.Body.Close()

	resp = doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/99999", map[string]any{"grade": 4})
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("missing id status = %d, want 404", resp.StatusCode)
	}
	resp.Body.Close()
}

func TestReviewStatsDigest(t *testing.T) {
	srv, st := newReviewTestServer(t)

	for i := 0; i < 2; i++ {
		if _, err := st.CreateNote(store.Note{Title: "n", Body: "b"}); err != nil {
			t.Fatalf("CreateNote: %v", err)
		}
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/stats", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("stats status = %d, want 200", resp.StatusCode)
	}
	var stats struct {
		DueToday   int     `json:"dueToday"`
		TotalNotes int     `json:"totalNotes"`
		Reviewed7d int     `json:"reviewed7d"`
		AvgEf      float64 `json:"avgEf"`
		StreakDays int     `json:"streakDays"`
	}
	decodeReviewJSON(t, resp, &stats)
	if stats.TotalNotes != 2 {
		t.Fatalf("totalNotes = %d, want 2", stats.TotalNotes)
	}
	if stats.DueToday < 0 {
		t.Fatalf("dueToday = %d, want >= 0", stats.DueToday)
	}

	resp = doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/digest?n=1", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("digest status = %d, want 200", resp.StatusCode)
	}
	var digest struct {
		Notes []struct {
			ID      int64    `json:"id"`
			Title   string   `json:"title"`
			Snippet string   `json:"snippet"`
			Tags    []string `json:"tags"`
			DueDate string   `json:"dueDate"`
		} `json:"notes"`
	}
	decodeReviewJSON(t, resp, &digest)
	if len(digest.Notes) != 1 {
		t.Fatalf("digest notes len = %d, want 1", len(digest.Notes))
	}
}

func TestReviewQueueShape(t *testing.T) {
	srv, st := newReviewTestServer(t)

	note, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatalf("CreateNote: %v", err)
	}
	tomorrow := time.Now().UTC().Add(24 * time.Hour)
	if _, err := st.RecordReview(note.ID, 4, tomorrow); err != nil {
		t.Fatalf("RecordReview: %v", err)
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/queue?limit=20", nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("queue status = %d, want 200", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	trimmed := bytes.TrimSpace(body)
	if !bytes.Equal(trimmed, []byte("[]")) {
		t.Fatalf("queue body = %s, want []", trimmed)
	}
}
