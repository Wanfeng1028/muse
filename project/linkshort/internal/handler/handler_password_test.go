package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
)

func postForm(t *testing.T, srv *httptest.Server, path string, form url.Values) *http.Response {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, srv.URL+path, strings.NewReader(form.Encode()))
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := noRedirectClient().Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	return resp
}

func readBody(t *testing.T, resp *http.Response) string {
	t.Helper()
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read body: %v", err)
	}
	return string(b)
}

func TestPassword_CreateLinkWithPassword(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	resp, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/secret",
		"slug":     "pw1",
		"password": "s3cr3t",
	})
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("create status = %d, body = %s", resp.StatusCode, string(body))
	}
	var created map[string]any
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("unmarshal create: %v", err)
	}
	if hp, ok := created["has_password"].(bool); !ok || !hp {
		t.Fatalf("has_password = %v, want true", created["has_password"])
	}
	if strings.Contains(string(body), "s3cr3t") {
		t.Fatalf("response leaks plaintext password: %s", string(body))
	}
	idNum, _ := created["id"].(float64)
	id := strconv.FormatInt(int64(idNum), 10)
	if idNum == 0 {
		t.Fatalf("missing id in create response: %s", string(body))
	}

	resp2, body2 := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id, testKey, nil)
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("get status = %d, body = %s", resp2.StatusCode, string(body2))
	}
	var got map[string]any
	if err := json.Unmarshal(body2, &got); err != nil {
		t.Fatalf("unmarshal get: %v", err)
	}
	if hp, ok := got["has_password"].(bool); !ok || !hp {
		t.Fatalf("get has_password = %v, want true", got["has_password"])
	}
}

func TestPassword_CreateLinkBadPassword(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	long := strings.Repeat("a", 129)
	resp, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/x",
		"slug":     "pwbad",
		"password": long,
	})
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400, body = %s", resp.StatusCode, string(body))
	}
}

func TestPassword_PatchSetClear(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":  "https://example.com/p",
		"slug": "pwpatch",
	})
	var created map[string]any
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("unmarshal create: %v", err)
	}
	idNum, _ := created["id"].(float64)
	id := strconv.FormatInt(int64(idNum), 10)
	if idNum == 0 {
		t.Fatalf("missing id: %s", string(body))
	}

	resp, body := doJSON(t, http.MethodPatch, srv.URL+"/api/links/"+id, testKey, map[string]any{
		"password": "newpw",
	})
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("patch set status = %d, body = %s", resp.StatusCode, string(body))
	}
	var setRes map[string]any
	if err := json.Unmarshal(body, &setRes); err != nil {
		t.Fatalf("unmarshal patch set: %v", err)
	}
	if hp, ok := setRes["has_password"].(bool); !ok || !hp {
		t.Fatalf("after set has_password = %v, want true", setRes["has_password"])
	}

	resp2, body2 := doJSON(t, http.MethodPatch, srv.URL+"/api/links/"+id, testKey, map[string]any{
		"password": "",
	})
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("patch clear status = %d, body = %s", resp2.StatusCode, string(body2))
	}
	var clearRes map[string]any
	if err := json.Unmarshal(body2, &clearRes); err != nil {
		t.Fatalf("unmarshal patch clear: %v", err)
	}
	if hp, ok := clearRes["has_password"].(bool); ok && hp {
		t.Fatalf("after clear has_password = %v, want false", clearRes["has_password"])
	}
}

func TestPassword_GatePage(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/gate-target",
		"slug":     "pwgate",
		"password": "pw",
	})
	if !strings.Contains(string(body), "\"id\"") {
		t.Fatalf("create failed: %s", string(body))
	}

	resp, err := noRedirectClient().Get(srv.URL + "/pwgate")
	if err != nil {
		t.Fatalf("get gate: %v", err)
	}
	page := readBody(t, resp)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("gate status = %d, body = %s", resp.StatusCode, page)
	}
	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "text/html") {
		t.Fatalf("content-type = %q, want text/html", ct)
	}
	if !strings.Contains(page, "<form") {
		t.Fatalf("gate body missing <form: %s", page)
	}
	if !strings.Contains(page, `method="post"`) {
		t.Fatalf("gate body missing method=\"post\": %s", page)
	}
	if strings.Contains(page, "https://example.com/gate-target") {
		t.Fatalf("gate page leaks target URL: %s", page)
	}
}

func TestPassword_WrongPassword(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/wrong",
		"slug":     "pwwrong",
		"password": "correct",
	})
	var created map[string]any
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("unmarshal create: %v", err)
	}
	idNum, _ := created["id"].(float64)
	id := strconv.FormatInt(int64(idNum), 10)
	if idNum == 0 {
		t.Fatalf("missing id: %s", string(body))
	}

	resp := postForm(t, srv, "/pwwrong", url.Values{"password": {"wrong"}})
	page := readBody(t, resp)
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401, body = %s", resp.StatusCode, page)
	}
	if !strings.Contains(page, "密码错误") {
		t.Fatalf("body missing 密码错误: %s", page)
	}

	_, gbody := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id, testKey, nil)
	var got map[string]any
	if err := json.Unmarshal(gbody, &got); err != nil {
		t.Fatalf("unmarshal get: %v", err)
	}
	if c, ok := got["clicks"].(float64); !ok || c != 0 {
		t.Fatalf("clicks = %v, want 0", got["clicks"])
	}
}

func TestPassword_CorrectPassword(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/correct-target",
		"slug":     "pwok",
		"password": "letmein",
	})
	var created map[string]any
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("unmarshal create: %v", err)
	}
	idNum, _ := created["id"].(float64)
	id := strconv.FormatInt(int64(idNum), 10)
	if idNum == 0 {
		t.Fatalf("missing id: %s", string(body))
	}

	resp := postForm(t, srv, "/pwok", url.Values{"password": {"letmein"}})
	io.Copy(io.Discard, resp.Body)
	resp.Body.Close()
	if resp.StatusCode != http.StatusFound {
		t.Fatalf("status = %d, want 302", resp.StatusCode)
	}
	if loc := resp.Header.Get("Location"); loc != "https://example.com/correct-target" {
		t.Fatalf("Location = %q, want target", loc)
	}

	_, gbody := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id, testKey, nil)
	var got map[string]any
	if err := json.Unmarshal(gbody, &got); err != nil {
		t.Fatalf("unmarshal get: %v", err)
	}
	if c, ok := got["clicks"].(float64); !ok || c != 1 {
		t.Fatalf("clicks = %v, want 1", got["clicks"])
	}
}

func TestPassword_BurnNotTriggeredByWrongPassword(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/burn-target",
		"slug":     "pwburn",
		"password": "burnpw",
		"burn":     true,
	})
	var created map[string]any
	if err := json.Unmarshal(body, &created); err != nil {
		t.Fatalf("unmarshal create: %v", err)
	}
	idNum, _ := created["id"].(float64)
	id := strconv.FormatInt(int64(idNum), 10)
	if idNum == 0 {
		t.Fatalf("missing id: %s", string(body))
	}

	wrong := postForm(t, srv, "/pwburn", url.Values{"password": {"nope"}})
	wbody := readBody(t, wrong)
	if wrong.StatusCode != http.StatusUnauthorized {
		t.Fatalf("wrong status = %d, want 401, body = %s", wrong.StatusCode, wbody)
	}

	correct := postForm(t, srv, "/pwburn", url.Values{"password": {"burnpw"}})
	io.Copy(io.Discard, correct.Body)
	correct.Body.Close()
	if correct.StatusCode != http.StatusFound {
		t.Fatalf("correct status = %d, want 302", correct.StatusCode)
	}

	_, gbody := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id, testKey, nil)
	var got map[string]any
	if err := json.Unmarshal(gbody, &got); err != nil {
		t.Fatalf("unmarshal get: %v", err)
	}
	if en, ok := got["enabled"].(bool); !ok || en {
		t.Fatalf("enabled = %v, want false after burn", got["enabled"])
	}
}

func TestPassword_Metrics(t *testing.T) {
	defer func(c int) { auth.BcryptCost = c }(auth.BcryptCost)
	auth.BcryptCost = bcrypt.MinCost

	srv := newTestServer(t)
	defer srv.Close()

	_, body := doJSON(t, http.MethodPost, srv.URL+"/api/links", testKey, map[string]any{
		"url":      "https://example.com/metrics-target",
		"slug":     "pwmetrics",
		"password": "metricpw",
	})
	if !strings.Contains(string(body), "\"id\"") {
		t.Fatalf("create failed: %s", string(body))
	}

	ok := postForm(t, srv, "/pwmetrics", url.Values{"password": {"metricpw"}})
	io.Copy(io.Discard, ok.Body)
	ok.Body.Close()
	if ok.StatusCode != http.StatusFound {
		t.Fatalf("ok status = %d, want 302", ok.StatusCode)
	}

	fail := postForm(t, srv, "/pwmetrics", url.Values{"password": {"bad"}})
	io.Copy(io.Discard, fail.Body)
	fail.Body.Close()
	if fail.StatusCode != http.StatusUnauthorized {
		t.Fatalf("fail status = %d, want 401", fail.StatusCode)
	}

	resp, mbody := doJSON(t, http.MethodGet, srv.URL+"/metrics", testKey, nil)
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("metrics status = %d, body = %s", resp.StatusCode, string(mbody))
	}
	ms := string(mbody)
	if !strings.Contains(ms, `linkshort_password_attempts_total{result="ok"}`) {
		t.Fatalf("metrics missing ok result line: %s", ms)
	}
	if !strings.Contains(ms, `linkshort_password_attempts_total{result="fail"}`) {
		t.Fatalf("metrics missing fail result line: %s", ms)
	}
}
