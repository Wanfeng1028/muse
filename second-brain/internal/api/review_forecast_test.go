package api

import (
	"net/http"
	"testing"
	"time"
)

type forecastEntry struct {
	Date string `json:"date"`
	Due  int    `json:"due"`
}

type reviewForecastResponse struct {
	Days     int             `json:"days"`
	Overdue  int             `json:"overdue"`
	Total    int             `json:"total"`
	Forecast []forecastEntry `json:"forecast"`
}

func TestReviewForecast_EmptyDB_Default(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/forecast", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}

	var got reviewForecastResponse
	decodeReviewJSON(t, resp, &got)

	if got.Days != 7 {
		t.Errorf("Days = %d, want 7", got.Days)
	}
	if len(got.Forecast) != 7 {
		t.Errorf("Forecast length = %d, want 7", len(got.Forecast))
	}
	if got.Overdue != 0 {
		t.Errorf("Overdue = %d, want 0", got.Overdue)
	}
	if got.Total != 0 {
		t.Errorf("Total = %d, want 0", got.Total)
	}
	for i, f := range got.Forecast {
		if f.Due != 0 {
			t.Errorf("Forecast[%d].Due = %d, want 0", i, f.Due)
		}
	}
	assertForecastDatesAscending(t, got.Forecast)
	assertFirstDateWithinDayCrossTolerance(t, got.Forecast)
}

func TestReviewForecast_Clamping(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	cases := []struct {
		query    string
		wantDays int
	}{
		{"days=0", 7},
		{"days=99", 30},
		{"days=3", 3},
	}

	for _, tc := range cases {
		t.Run(tc.query, func(t *testing.T) {
			resp := doReviewJSON(t, http.MethodGet, srv.URL+"/api/review/forecast?"+tc.query, nil)
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				t.Fatalf("expected status 200, got %d", resp.StatusCode)
			}

			var got reviewForecastResponse
			decodeReviewJSON(t, resp, &got)

			if got.Days != tc.wantDays {
				t.Errorf("Days = %d, want %d", got.Days, tc.wantDays)
			}
			if len(got.Forecast) != tc.wantDays {
				t.Errorf("Forecast length = %d, want %d", len(got.Forecast), tc.wantDays)
			}
			assertForecastDatesAscending(t, got.Forecast)
			assertFirstDateWithinDayCrossTolerance(t, got.Forecast)
		})
	}
}

func TestReviewForecast_MethodNotAllowed(t *testing.T) {
	srv, _ := newReviewTestServer(t)
	resp := doReviewJSON(t, http.MethodPost, srv.URL+"/api/review/forecast", nil)
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusMethodNotAllowed {
		t.Fatalf("expected status 405, got %d", resp.StatusCode)
	}
}

func assertForecastDatesAscending(t *testing.T, entries []forecastEntry) {
	t.Helper()
	for i := 1; i < len(entries); i++ {
		if entries[i].Date <= entries[i-1].Date {
			t.Errorf("Forecast[%d].Date = %q not after Forecast[%d].Date = %q",
				i, entries[i].Date, i-1, entries[i-1].Date)
		}
	}
}

func assertFirstDateWithinDayCrossTolerance(t *testing.T, entries []forecastEntry) {
	t.Helper()
	if len(entries) == 0 {
		return
	}
	today := time.Now().UTC().Format("2006-01-02")
	yesterday := time.Now().UTC().AddDate(0, 0, -1).Format("2006-01-02")
	first := entries[0].Date
	if first != today && first != yesterday {
		t.Errorf("Forecast[0].Date = %q, want %q or %q", first, today, yesterday)
	}
}
