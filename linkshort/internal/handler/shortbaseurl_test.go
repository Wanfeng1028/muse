package handler

import (
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
)

func TestShortBaseURLTrimsSpaces(t *testing.T) {
	req := httptest.NewRequest("GET", "http://req.test/", nil)

	tests := []struct {
		name    string
		baseURL string
		want    string
	}{
		{"case 1", "https://s.example.com", "https://s.example.com"},
		{"case 2", "https://s.example.com/", "https://s.example.com"},
		{"case 3", "  https://s.example.com  ", "https://s.example.com"},
		{"case 4", "https://s.example.com/  ", "https://s.example.com"},
		{"case 5", "   ", "http://req.test"},
		{"case 6", "", "http://req.test"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := &config.Config{BaseURL: tt.baseURL}
			got := shortBaseURL(req, cfg)
			if got != tt.want {
				t.Fatalf("case %q: got %q, want %q", tt.name, got, tt.want)
			}
		})
	}
}
