package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
	"github.com/go-chi/chi/v5"
)

// 仅供本文件使用的测试路由：直挂 handleStatsHourly，不走鉴权。
func newHourlyTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	database, err := db.Open(":memory:")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	st := store.New(database)

	r := chi.NewRouter()
	r.Route("/api", func(api chi.Router) {
		api.Get("/stats/hourly", func(w http.ResponseWriter, req *http.Request) { handleStatsHourly(w, req, st) })
	})
	ts := httptest.NewServer(r)
	t.Cleanup(func() {
		ts.Close()
		database.Close()
	})
	return ts, st
}

func getHourlyStats(t *testing.T, url string) map[string]any {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return body
}

func TestHandleStatsHourly_基本(t *testing.T) {
	ts, st := newHourlyTestServer(t)
	id, err := st.CreateLinkEx("hh1", "https://example.com", "", nil, nil, false, false)
	if err != nil {
		t.Fatalf("create link: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := st.RecordVisitGeo(id, "h", "ua", "", "", "", "", ""); err != nil {
			t.Fatalf("record visit: %v", err)
		}
	}

	body := getHourlyStats(t, ts.URL+"/api/stats/hourly?days=1")
	hours, ok := body["hours"].([]any)
	if !ok {
		t.Fatalf("hours not array: %v", body["hours"])
	}
	if len(hours) != 24 {
		t.Fatalf("hours len = %d, want 24", len(hours))
	}
	if tc, _ := body["total_clicks"].(float64); int64(tc) != 3 {
		t.Fatalf("total_clicks = %v, want 3", body["total_clicks"])
	}

	body2 := getHourlyStats(t, ts.URL+"/api/stats/hourly?days=7&link_id="+itoa(id))
	if tc, _ := body2["total_clicks"].(float64); int64(tc) != 3 {
		t.Fatalf("total_clicks = %v, want 3", body2["total_clicks"])
	}
}

func TestHandleStatsHourly_days回落(t *testing.T) {
	ts, _ := newHourlyTestServer(t)
	body := getHourlyStats(t, ts.URL+"/api/stats/hourly?days=999")
	if d, _ := body["days"].(float64); int(d) != 30 {
		t.Fatalf("days = %v, want 30", body["days"])
	}
}

func TestHandleStatsHourly_负linkID(t *testing.T) {
	ts, _ := newHourlyTestServer(t)
	resp, err := http.Get(ts.URL + "/api/stats/hourly?link_id=-5")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
}
