package api

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

type heatmapResp struct {
	Days    int `json:"days"`
	Heatmap []struct {
		Date     string `json:"date"`
		Reviewed int    `json:"reviewed"`
		Added    int    `json:"added"`
	} `json:"heatmap"`
}

func TestReviewHeatmapAPI_Default(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/heatmap", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected 200, got %d", resp.StatusCode)
	}

	var v heatmapResp
	decodeReviewJSON(t, resp, &v)

	if v.Days != 365 {
		t.Errorf("expected Days 365, got %d", v.Days)
	}
	if len(v.Heatmap) != 365 {
		t.Errorf("expected len(Heatmap) 365, got %d", len(v.Heatmap))
	}
	today := time.Now().UTC().Format("2006-01-02")
	if len(v.Heatmap) > 0 && v.Heatmap[len(v.Heatmap)-1].Date != today {
		t.Errorf("expected last date %s, got %s", today, v.Heatmap[len(v.Heatmap)-1].Date)
	}
}

func TestReviewHeatmapAPI_Clamp(t *testing.T) {
	srv, _ := newReviewTestServer(t)

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/heatmap?days=400", nil)
	defer resp.Body.Close()

	var v1 heatmapResp
	decodeReviewJSON(t, resp, &v1)
	if v1.Days != 366 {
		t.Errorf("expected Days 366, got %d", v1.Days)
	}
	if len(v1.Heatmap) != 366 {
		t.Errorf("expected len(Heatmap) 366, got %d", len(v1.Heatmap))
	}

	resp2 := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/heatmap?days=abc", nil)
	defer resp2.Body.Close()

	var v2 heatmapResp
	decodeReviewJSON(t, resp2, &v2)
	if v2.Days != 365 {
		t.Errorf("expected Days 365, got %d", v2.Days)
	}
}

func TestReviewHeatmapAPI_UserIsolation(t *testing.T) {
	srv, st := newReviewTestServer(t)
	today := time.Now().UTC().Format("2006-01-02")

	n1, err := st.CreateNote(store.Note{Title: "n1", Body: "b1"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.RecordReview(context.Background(), n1.ID, 4, time.Now(), "local"); err != nil {
		t.Fatal(err)
	}

	n2, err := st.CreateNote(store.Note{Title: "n2", Body: "b2"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.RecordReview(context.Background(), n2.ID, 4, time.Now(), "u2"); err != nil {
		t.Fatal(err)
	}

	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/heatmap", nil)
	defer resp.Body.Close()
	var vLocal heatmapResp
	decodeReviewJSON(t, resp, &vLocal)

	var localReviewed int
	for _, d := range vLocal.Heatmap {
		if d.Date == today {
			localReviewed = d.Reviewed
			break
		}
	}
	if localReviewed != 1 {
		t.Errorf("expected local reviewed 1, got %d", localReviewed)
	}

	respU2 := doReviewJSONUser(t, http.MethodGet, srv.URL+"/api/review/heatmap", nil, "u2")
	defer respU2.Body.Close()
	var vU2 heatmapResp
	decodeReviewJSON(t, respU2, &vU2)

	var u2Reviewed int
	for _, d := range vU2.Heatmap {
		if d.Date == today {
			u2Reviewed = d.Reviewed
			break
		}
	}
	if u2Reviewed != 1 {
		t.Errorf("expected u2 reviewed 1, got %d", u2Reviewed)
	}
}
