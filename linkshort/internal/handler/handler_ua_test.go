package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

const (
	uaDesktopChrome = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
	uaIPhoneWeChat  = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40(0x18002832) NetType/WIFI Language/zh_CN"
)

func hitWithUA(t *testing.T, srv *httptest.Server, slug, ua string) {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, srv.URL+"/"+slug, nil)
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("User-Agent", ua)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("hit slug %s: %v", slug, err)
	}
	resp.Body.Close()
}

func decodeUA(t *testing.T, srv *httptest.Server, id int64) map[string]any {
	t.Helper()
	resp, data := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+itoa(id)+"/ua", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("ua status = %d, want 200", resp.StatusCode)
	}
	var out map[string]any
	if err := json.Unmarshal(data, &out); err != nil {
		t.Fatalf("unmarshal ua: %v", err)
	}
	return out
}

func namedStatList(t *testing.T, v any) []map[string]any {
	t.Helper()
	raw, ok := v.([]any)
	if !ok {
		t.Fatalf("expected list, got %T", v)
	}
	out := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		m, ok := item.(map[string]any)
		if !ok {
			t.Fatalf("expected map item, got %T", item)
		}
		out = append(out, m)
	}
	return out
}

func findNamed(t *testing.T, list []map[string]any, name string) map[string]any {
	t.Helper()
	for _, m := range list {
		if m["name"] == name {
			return m
		}
	}
	return nil
}

func TestLinkUAEmpty(t *testing.T) {
	srv := newTestServer(t)
	cfg := newTestConfig(t)
	cfg.AdminKey = testKey
	created := createLink(t, srv, cfg, map[string]any{"url": "https://example.com/ua-empty"})
	id := int64(created["id"].(float64))

	body := decodeUA(t, srv, id)
	if got := body["link_id"].(float64); int64(got) != id {
		t.Fatalf("link_id = %v, want %d", got, id)
	}
	if got := body["total"].(float64); got != 0 {
		t.Fatalf("total = %v, want 0", got)
	}
	if got := body["bots"].(float64); got != 0 {
		t.Fatalf("bots = %v, want 0", got)
	}
	for _, key := range []string{"devices", "browsers", "os"} {
		list := namedStatList(t, body[key])
		if len(list) != 0 {
			t.Fatalf("%s len = %d, want 0", key, len(list))
		}
	}
}

func TestLinkUATwoHits(t *testing.T) {
	srv := newTestServer(t)
	cfg := newTestConfig(t)
	cfg.AdminKey = testKey
	created := createLink(t, srv, cfg, map[string]any{"url": "https://example.com/ua-two"})
	id := int64(created["id"].(float64))
	slug := created["slug"].(string)

	hitWithUA(t, srv, slug, uaDesktopChrome)
	hitWithUA(t, srv, slug, uaIPhoneWeChat)

	body := decodeUA(t, srv, id)
	if got := body["total"].(float64); got != 2 {
		t.Fatalf("total = %v, want 2", got)
	}

	devices := namedStatList(t, body["devices"])
	mobile := findNamed(t, devices, "\u624b\u673a")
	desktop := findNamed(t, devices, "\u684c\u9762")
	if mobile == nil {
		t.Fatalf("devices missing \u624b\u673a: %v", devices)
	}
	if desktop == nil {
		t.Fatalf("devices missing \u684c\u9762: %v", devices)
	}
	if got := mobile["clicks"].(float64); got != 1 {
		t.Fatalf("mobile clicks = %v, want 1", got)
	}
	if got := desktop["clicks"].(float64); got != 1 {
		t.Fatalf("desktop clicks = %v, want 1", got)
	}

	browsers := namedStatList(t, body["browsers"])
	if findNamed(t, browsers, "Chrome") == nil {
		t.Fatalf("browsers missing Chrome: %v", browsers)
	}
	if findNamed(t, browsers, "\u5fae\u4fe1") == nil {
		t.Fatalf("browsers missing \u5fae\u4fe1: %v", browsers)
	}

	osList := namedStatList(t, body["os"])
	if findNamed(t, osList, "Windows") == nil {
		t.Fatalf("os missing Windows: %v", osList)
	}
	if findNamed(t, osList, "iOS") == nil {
		t.Fatalf("os missing iOS: %v", osList)
	}
}

func TestLinkUABadID(t *testing.T) {
	srv := newTestServer(t)

	resp, _ := doJSON(t, http.MethodGet, srv.URL+"/api/links/abc/ua", testKey, nil)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", resp.StatusCode)
	}
}

func TestLinkUAMissingID(t *testing.T) {
	srv := newTestServer(t)

	out := decodeUA(t, srv, 99999)
	if got := out["total"].(float64); got != 0 {
		t.Fatalf("total = %v, want 0", got)
	}
	for _, key := range []string{"devices", "browsers", "os"} {
		list := namedStatList(t, out[key])
		if len(list) != 0 {
			t.Fatalf("%s len = %d, want 0", key, len(list))
		}
	}
}
