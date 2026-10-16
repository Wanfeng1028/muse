package api

import (
	"encoding/json"
	"io"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
	"github.com/Wanfeng1028/muse/second-brain/internal/web"
)

func fsStat(fsys fs.FS, name string) (fs.FileInfo, error) {
	return fs.Stat(fsys, name)
}

func newPwaTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })
	var cfg config.Config
	srv := httptest.NewServer(NewServer(st, cfg))
	t.Cleanup(srv.Close)
	return srv
}

func getBody(t *testing.T, url string) (*http.Response, []byte) {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("GET %s: %v", url, err)
	}
	t.Cleanup(func() { _ = resp.Body.Close() })
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body %s: %v", url, err)
	}
	return resp, body
}

func TestManifestServed(t *testing.T) {
	srv := newPwaTestServer(t)
	resp, body := getBody(t, srv.URL+"/manifest.webmanifest")

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/manifest+json") {
		t.Fatalf("Content-Type = %q, want contains application/manifest+json", ct)
	}

	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		t.Fatalf("manifest body is not valid JSON: %v", err)
	}

	for _, key := range []string{"name", "short_name", "start_url", "display", "icons"} {
		if _, ok := m[key]; !ok {
			t.Errorf("manifest missing field %q", key)
		}
	}

	if disp, _ := m["display"].(string); disp != "standalone" {
		t.Errorf("display = %q, want standalone", disp)
	}

	iconsAny, ok := m["icons"].([]any)
	if !ok {
		t.Fatalf("icons is not an array: %T", m["icons"])
	}
	if len(iconsAny) == 0 {
		t.Fatalf("icons array is empty")
	}

	staticFS := web.StaticFS()
	for i, iconAny := range iconsAny {
		icon, ok := iconAny.(map[string]any)
		if !ok {
			t.Fatalf("icons[%d] is not an object: %T", i, iconAny)
		}
		src, _ := icon["src"].(string)
		if src == "" {
			t.Errorf("icons[%d].src is empty", i)
			continue
		}
		sizes, _ := icon["sizes"].(string)
		if sizes == "" {
			t.Errorf("icons[%d].sizes is empty", i)
		}
		if _, err := fsStat(staticFS, src); err != nil {
			t.Errorf("icons[%d].src %q not found in StaticFS: %v", i, src, err)
		}
	}
}

func TestServiceWorkerServed(t *testing.T) {
	srv := newPwaTestServer(t)
	resp, body := getBody(t, srv.URL+"/sw.js")

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "javascript") {
		t.Fatalf("Content-Type = %q, want contains javascript", ct)
	}
	if got := resp.Header.Get("Service-Worker-Allowed"); got != "/" {
		t.Fatalf("Service-Worker-Allowed = %q, want /", got)
	}
	if got := resp.Header.Get("Cache-Control"); got != "no-cache" {
		t.Fatalf("Cache-Control = %q, want no-cache", got)
	}

	s := string(body)
	if !strings.Contains(s, "CACHE_NAME") {
		t.Errorf("sw.js body does not contain CACHE_NAME")
	}
	if !strings.Contains(s, "SKIP_WAITING") {
		t.Errorf("sw.js body does not contain SKIP_WAITING")
	}
}

func TestPwaCacheListMatchesFiles(t *testing.T) {
	srv := newPwaTestServer(t)
	resp, body := getBody(t, srv.URL+"/sw.js")
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}

	src := string(body)

	// Extract the APP_SHELL array literal.
	appShellRe := regexp.MustCompile(`(?s)APP_SHELL\s*=\s*\[(.*?)\]`)
	m := appShellRe.FindStringSubmatch(src)
	if m == nil {
		t.Fatalf("could not find APP_SHELL array in sw.js")
	}
	arrayBody := m[1]

	pathRe := regexp.MustCompile(`["'](/[^"']*)["']`)
	matches := pathRe.FindAllStringSubmatch(arrayBody, -1)
	if len(matches) == 0 {
		t.Fatalf("APP_SHELL array contains no paths")
	}

	staticFS := web.StaticFS()
	for _, mm := range matches {
		p := mm[1]
		var rel string
		switch {
		case p == "/":
			rel = "index.html"
		case strings.HasPrefix(p, "/static/"):
			rel = strings.TrimPrefix(p, "/static/")
		default:
			// Not a static-served path we can verify against StaticFS.
			continue
		}
		if _, err := fsStat(staticFS, rel); err != nil {
			t.Errorf("APP_SHELL path %q (rel %q) not found in StaticFS: %v", p, rel, err)
		}
	}
}
