package handlers

import (
	"net/http"
	"testing"
)

func TestHandleListIncidentsPaginationValidationDeep3(t *testing.T) {
	srv, _ := newTestServer(t)
	h := srv.Routes()

	type deep3Case struct {
		name     string
		query    string
		wantCode int
	}

	cases := []deep3Case{
		{name: "page=abc returns 400", query: "?page=abc", wantCode: http.StatusBadRequest},
		{name: "per_page=abc returns 400", query: "?per_page=abc", wantCode: http.StatusBadRequest},
		{name: "page_size=xyz returns 400", query: "?page_size=xyz", wantCode: http.StatusBadRequest},
		{name: "limit=zzz returns 400", query: "?limit=zzz", wantCode: http.StatusBadRequest},
		{name: "valid pagination returns 200 with items", query: "?page=1&per_page=10", wantCode: http.StatusOK},
	}

	for _, tc := range cases {
		url := "/api/incidents" + tc.query
		rec, body := deep3DoJSON(t, h, http.MethodGet, url, "")

		if rec.Code != tc.wantCode {
			t.Fatalf("%s: query=%q: got status %d, want %d, body=%v", tc.name, tc.query, rec.Code, tc.wantCode, body)
		}
	}

	rec, body := deep3DoJSON(t, h, http.MethodGet, "/api/incidents?page=1&per_page=10", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("valid pagination: query=%q: got status %d, want %d, body=%v", "page=1&per_page=10", rec.Code, http.StatusOK, body)
	}

	items, ok := body["items"].([]interface{})
	if !ok {
		t.Fatalf("valid pagination: query=%q: status=%d, body[\"items\"] is not an array, body=%v", "page=1&per_page=10", rec.Code, body)
	}
	_ = items
}
