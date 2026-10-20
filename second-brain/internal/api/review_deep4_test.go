package api

import (
	"io"
	"net/http"
	"strconv"
	"strings"
	"testing"
)

func TestReviewGradeInvalidJSON(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	noteID := createNoteAs(t, srv.URL, "g3", "note")

	req, err := http.NewRequest(http.MethodPost, srv.URL+"/api/review/"+strconv.FormatInt(noteID, 10), strings.NewReader("not-json{"))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), "invalid body") {
		t.Errorf("expected invalid body, got %s", body)
	}
}

func TestReviewQueuePostRejected(t *testing.T) {
	srv, _ := newReviewTestServer(t)

	resp := doReviewJSONUser(t, http.MethodPost, srv.URL+"/api/review/queue", nil, "g6")
	defer resp.Body.Close()

	// 实际行为：POST 到只读队列端点返回 400（非 405），锁定该行为
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}
}


func TestReviewTrendDaysClamp(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	_ = createNoteAs(t, srv.URL, "g5", "note")

	// days=0
	resp, err := http.Get(srv.URL + "/api/review/trend?days=0")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}
	var body map[string]any
	decodeReviewJSON(t, resp, &body)
	if body["days"] != float64(7) {
		t.Errorf("expected days 7, got %v", body["days"])
	}
	resp.Body.Close()

	// days=1000
	resp, err = http.Get(srv.URL + "/api/review/trend?days=1000")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}
	body = nil
	decodeReviewJSON(t, resp, &body)
	if body["days"] != float64(60) {
		t.Errorf("expected days 60, got %v", body["days"])
	}
	resp.Body.Close()

	// no params
	resp, err = http.Get(srv.URL + "/api/review/trend")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}
	body = nil
	decodeReviewJSON(t, resp, &body)
	if body["days"] != float64(7) {
		t.Errorf("expected days 7, got %v", body["days"])
	}
	resp.Body.Close()
}

func TestReviewGradeResponseReviewedCount(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	noteID := createNoteAs(t, srv.URL, "g4", "note")

	resp := doReviewJSONUser(t, http.MethodPost, srv.URL+"/api/review/"+strconv.FormatInt(noteID, 10), map[string]any{"grade": 3}, "g4")
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}

	var body map[string]any
	decodeReviewJSON(t, resp, &body)

	if body["reviewedCount"] != float64(1) {
		t.Errorf("expected reviewedCount 1, got %v", body["reviewedCount"])
	}

	for _, key := range []string{"ef", "intervalDays", "repetitions", "dueDate"} {
		if _, ok := body[key]; !ok {
			t.Errorf("missing key %s", key)
		}
	}
}

func TestReviewGradeBoundaryFive(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	noteID := createNoteAs(t, srv.URL, "g2", "note")

	resp := doReviewJSONUser(t, http.MethodPost, srv.URL+"/api/review/"+strconv.FormatInt(noteID, 10), map[string]any{"grade": 5}, "g2")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected 200, got %d", resp.StatusCode)
	}

	resp = doReviewJSONUser(t, http.MethodPost, srv.URL+"/api/review/"+strconv.FormatInt(noteID, 10), map[string]any{"grade": 6}, "g2")
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), "invalid grade") {
		t.Errorf("expected invalid grade, got %s", body)
	}
}

func TestReviewGradeMissingGradeField(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	noteID := createNoteAs(t, srv.URL, "g1", "note")

	resp := doReviewJSONUser(t, http.MethodPost, srv.URL+"/api/review/"+strconv.FormatInt(noteID, 10), map[string]any{}, "g1")
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), "invalid grade") {
		t.Errorf("expected invalid grade, got %s", body)
	}
}

