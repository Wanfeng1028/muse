package handler

import (
	"net/http"
	"strings"
	"testing"
)

func TestLinkReferersNValidation(t *testing.T) {
	srv := newTestServer(t)

	tests := []struct {
		name       string
		urlSuffix  string
		wantStatus int
		wantBody   string
	}{
		{name: "n_abc", urlSuffix: "?n=abc", wantStatus: http.StatusBadRequest, wantBody: "n 非法"},
		{name: "n_float", urlSuffix: "?n=1.5", wantStatus: http.StatusBadRequest, wantBody: "n 非法"},
		{name: "n_suffix", urlSuffix: "?n=1x", wantStatus: http.StatusBadRequest, wantBody: "n 非法"},
		{name: "n_missing", urlSuffix: "", wantStatus: http.StatusOK, wantBody: ""},
		{name: "n_zero_clamp", urlSuffix: "?n=0", wantStatus: http.StatusOK, wantBody: ""},
		{name: "n_valid", urlSuffix: "?n=8", wantStatus: http.StatusOK, wantBody: ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, id := c2MakeLink(t, srv)
			url := srv.URL + "/api/links/" + id + "/referers" + tt.urlSuffix
			resp, body := doJSON(t, http.MethodGet, url, testKey, nil)
			if resp.StatusCode != tt.wantStatus {
				t.Fatalf("[%s] status: got %d, want %d, body: %s", tt.name, resp.StatusCode, tt.wantStatus, string(body))
			}
			if tt.wantBody != "" && !strings.Contains(string(body), tt.wantBody) {
				t.Fatalf("[%s] body: got %s, want contains %q", tt.name, string(body), tt.wantBody)
			}
		})
	}
}
