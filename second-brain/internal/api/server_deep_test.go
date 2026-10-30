package api

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newDeepTestServer(t *testing.T) (*store.Store, http.Handler) {
	t.Helper()
	st, err := store.Open(filepath.Join(t.TempDir(), "muse.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return st, NewServer(st, config.Config{})
}

func doJSONServer(t *testing.T, h http.Handler, method, target string, body any, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var rd io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rd = bytes.NewReader(raw)
	}
	req := httptest.NewRequest(method, target, rd)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func createNote(t *testing.T, h http.Handler, n store.Note) store.Note {
	t.Helper()
	rec := doJSONServer(t, h, http.MethodPost, "/api/notes", n, nil)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create note: status=%d body=%s", rec.Code, rec.Body.String())
	}
	var out store.Note
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode created note: %v", err)
	}
	return out
}

func TestBacklinkParsingBoundaries(t *testing.T) {
	st, h := newDeepTestServer(t)
	target := createNote(t, h, store.Note{Title: "目标笔记", Body: "内容"})
	cases := []struct {
		name     string
		body     string
		wantLink bool
	}{
		{"plain link", "见 [[" + target.Title + "]]", true},
		{"nested brackets", "见 [[[[" + target.Title + "]]]]", false},
		{"chinese title", "见 [[" + target.Title + "]]", true},
		{"partial bracket", "见 [[目标笔记", false},
		{"empty link", "见 [[]]", false},
		{"unrelated", "见 [[别的笔记]]", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			n := createNote(t, h, store.Note{Title: "引用-" + tc.name, Body: tc.body})
			_ = n
			bl, err := st.Backlinks(target.ID)
			if err != nil {
				t.Fatalf("backlinks: %v", err)
			}
			found := false
			for _, b := range bl {
				if strings.Contains(b.Title, tc.name) {
					found = true
				}
			}
			if found != tc.wantLink {
				t.Fatalf("backlink found=%v want=%v bl=%+v", found, tc.wantLink, bl)
			}
			if tc.wantLink && len(bl) == 0 {
				t.Fatalf("expected at least one backlink, got none")
			}
		})
	}
}

func TestExportZipSlipServer(t *testing.T) {
	h := NewServer(newStore(t), config.Config{})
	rec := doJSONServer(t, h, http.MethodGet, "/api/export/markdown", nil, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("export status: got %d body=%s", rec.Code, rec.Body.String())
	}
	raw := rec.Body.Bytes()
	if len(raw) == 0 {
		t.Fatalf("export returned empty body")
	}
	zr, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil {
		t.Fatalf("zip reader: %v", err)
	}
	for _, f := range zr.File {
		clean := filepath.ToSlash(filepath.Clean(f.Name))
		if strings.HasPrefix(clean, "..") {
			t.Fatalf("zip slip entry: %s", f.Name)
		}
		if filepath.IsAbs(f.Name) {
			t.Fatalf("absolute zip entry: %s", f.Name)
		}
	}
	if len(zr.File) == 0 {
		t.Fatalf("zip has zero entries")
	}
}

func TestSearchQueryTermsChinese(t *testing.T) {
	h := NewServer(newStore(t), config.Config{})
	cases := []struct {
		name     string
		query    string
		wantCode int
	}{
		{"chinese", "笔记", http.StatusOK},
		{"empty", "", http.StatusOK},
		{"whitespace", "   ", http.StatusOK},
		{"mixed", "go 笔记 test", http.StatusOK},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := doJSONServer(t, h, http.MethodGet, "/api/search?q="+url.QueryEscape(tc.query), nil, nil)
			if rec.Code != tc.wantCode {
				t.Fatalf("status: got %d want %d body=%s", rec.Code, tc.wantCode, rec.Body.String())
			}
			var out map[string]any
			if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
				t.Fatalf("decode: %v", err)
			}
			if _, ok := out["terms"]; !ok {
				t.Fatalf("missing terms field: %v", out)
			}
			if _, ok := out["notes"]; !ok {
				t.Fatalf("missing notes field: %v", out)
			}
		})
	}
}

func TestNotesListLimitOffsetNegative400(t *testing.T) {
	h := NewServer(newStore(t), config.Config{})
	cases := []struct {
		name     string
		target   string
		wantCode int
		wantErr  string
	}{
		{"negative limit", "/api/notes?limit=-5", http.StatusBadRequest, "limit 参数非法"},
		{"negative offset", "/api/notes?offset=-10", http.StatusBadRequest, "offset 参数非法"},
		{"limit non-numeric", "/api/notes?limit=abc", http.StatusBadRequest, "limit 参数非法"},
		{"limit decimal", "/api/notes?limit=1.5", http.StatusBadRequest, "limit 参数非法"},
		{"limit mixed", "/api/notes?limit=1x", http.StatusBadRequest, "limit 参数非法"},
		{"offset non-numeric", "/api/notes?offset=abc", http.StatusBadRequest, "offset 参数非法"},
		{"offset decimal", "/api/notes?offset=1.5", http.StatusBadRequest, "offset 参数非法"},
		{"offset mixed", "/api/notes?offset=1x", http.StatusBadRequest, "offset 参数非法"},
		{"huge limit", "/api/notes?limit=100000", http.StatusOK, ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := doJSONServer(t, h, http.MethodGet, tc.target, nil, nil)
			if rec.Code != tc.wantCode {
				t.Fatalf("status: got %d want %d body=%s", rec.Code, tc.wantCode, rec.Body.String())
			}
			if tc.wantErr != "" {
				var errOut struct {
					Error string `json:"error"`
				}
				if err := json.Unmarshal(rec.Body.Bytes(), &errOut); err != nil {
					t.Fatalf("decode error response: %v", err)
				}
				if !strings.Contains(errOut.Error, tc.wantErr) {
					t.Fatalf("error: got %q want substring %q", errOut.Error, tc.wantErr)
				}
				return
			}
			var out []store.Note
			if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
				t.Fatalf("decode: %v", err)
			}
			if out == nil {
				t.Fatalf("expected non-nil slice, got nil")
			}
		})
	}
}

func TestMetricsTokenAuth(t *testing.T) {
	st, _ := newDeepTestServer(t)
	_ = st
	cfg := config.Config{}
	cfg.Metrics.Enabled = true
	cfg.Metrics.Token = "secret-token"
	h := NewServer(st, cfg)

	cases := []struct {
		name     string
		header   string
		wantCode int
	}{
		{"no auth", "", http.StatusUnauthorized},
		{"wrong token", "Bearer nope", http.StatusUnauthorized},
		{"right token", "Bearer secret-token", http.StatusOK},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			headers := map[string]string{}
			if tc.header != "" {
				headers["Authorization"] = tc.header
			}
			rec := doJSONServer(t, h, http.MethodGet, "/metrics", nil, headers)
			if rec.Code != tc.wantCode {
				t.Fatalf("status: got %d want %d body=%s", rec.Code, tc.wantCode, rec.Body.String())
			}
			if tc.wantCode == http.StatusOK && rec.Body.Len() == 0 {
				t.Fatalf("metrics body should not be empty")
			}
		})
	}
}

func newStore(t *testing.T) *store.Store {
	t.Helper()
	st, err := store.Open(filepath.Join(t.TempDir(), "muse.db"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return st
}

func createNoteWithUser(t *testing.T, h http.Handler, user string, n store.Note) store.Note {
	t.Helper()
	raw, err := json.Marshal(n)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	req := httptest.NewRequest(http.MethodPost, "/api/notes", bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User", user)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create note user=%s status=%d body=%s", user, rec.Code, rec.Body.String())
	}
	var out store.Note
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if out.ID == 0 {
		t.Fatalf("expected non-zero id for user=%s", user)
	}
	return out
}

func TestBacklinksResponseShape(t *testing.T) {
	h := NewServer(newStore(t), config.Config{})
	target := createNote(t, h, store.Note{Title: "形状目标", Body: "x"})
	createNote(t, h, store.Note{Title: "形状引用", Body: "见 [[形状目标]]"})
	rec := doJSONServer(t, h, http.MethodGet, fmt.Sprintf("/api/notes/%d/backlinks", target.ID), nil, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status: got %d body=%s", rec.Code, rec.Body.String())
	}
	var bl []store.Note
	if err := json.Unmarshal(rec.Body.Bytes(), &bl); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(bl) != 1 {
		t.Fatalf("expected 1 backlink, got %d: %+v", len(bl), bl)
	}
	if bl[0].Title != "形状引用" {
		t.Fatalf("unexpected backlink title: %q", bl[0].Title)
	}
}
