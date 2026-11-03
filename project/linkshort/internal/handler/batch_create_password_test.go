package handler

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
)

func batchPasswordTestCost(t *testing.T) {
	t.Helper()
	old := auth.BcryptCost
	auth.BcryptCost = bcrypt.MinCost
	t.Cleanup(func() { auth.BcryptCost = old })
}

func TestBatch_PasswordSuccess(t *testing.T) {
	batchPasswordTestCost(t)
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/pw1", "slug": "bpw1", "password": "s3cr3t-pw"},
		{"url": "https://a.com/plain1", "slug": "bplain1"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status = %d, want 201, body = %s", resp.StatusCode, string(data))
	}
	if strings.Contains(string(data), "s3cr3t-pw") {
		t.Fatalf("batch response leaks plaintext password: %s", string(data))
	}
	m, items := parseBatch(t, data)
	if got := batchOKCount(m); got != 2 {
		t.Fatalf("ok_count = %d, want 2", got)
	}
	if !batchOK(items[0]) {
		t.Fatalf("items[0].ok = false, error = %q, want true", batchErr(items[0]))
	}
	id := strconv.FormatInt(batchID(items[0]), 10)
	resp2, body2 := doJSON(t, http.MethodGet, srv.URL+"/api/links/"+id, testKey, nil)
	if resp2.StatusCode != http.StatusOK {
		t.Fatalf("get status = %d, body = %s", resp2.StatusCode, string(body2))
	}
	var got map[string]any
	if err := json.Unmarshal(body2, &got); err != nil {
		t.Fatalf("unmarshal get: %v", err)
	}
	if hp, ok := got["has_password"].(bool); !ok || !hp {
		t.Fatalf("has_password = %v, want true", got["has_password"])
	}
	if strings.Contains(string(body2), "s3cr3t-pw") {
		t.Fatalf("get response leaks plaintext password: %s", string(body2))
	}
}

func TestBatch_PasswordTooLongPartial(t *testing.T) {
	batchPasswordTestCost(t)
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/pwlong", "slug": "bpwlong", "password": strings.Repeat("x", 129)},
		{"url": "https://a.com/pwok", "slug": "bpwok"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusMultiStatus {
		t.Fatalf("status = %d, want 207, body = %s", resp.StatusCode, string(data))
	}
	m, items := parseBatch(t, data)
	if got := batchOKCount(m); got != 1 {
		t.Fatalf("ok_count = %d, want 1", got)
	}
	if batchOK(items[0]) {
		t.Fatalf("items[0].ok = true, want false")
	}
	if !strings.Contains(batchErr(items[0]), "密码") {
		t.Fatalf("items[0].error = %q, want contains 密码", batchErr(items[0]))
	}
	if !batchOK(items[1]) {
		t.Fatalf("items[1].ok = false, error = %q, want true", batchErr(items[1]))
	}
}

func TestBatch_PasswordGate(t *testing.T) {
	batchPasswordTestCost(t)
	srv := newTestServerWithPurge(t, false)
	defer srv.Close()

	body := []map[string]any{
		{"url": "https://a.com/gated", "slug": "bpwgate", "password": "gate-pw"},
	}
	resp, data := doJSON(t, http.MethodPost, srv.URL+"/api/links/batch", testKey, body)
	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("status = %d, want 201, body = %s", resp.StatusCode, string(data))
	}

	req, err := http.NewRequest(http.MethodGet, srv.URL+"/bpwgate", nil)
	if err != nil {
		t.Fatalf("build get request: %v", err)
	}
	gateResp, err := noRedirectClient().Do(req)
	if err != nil {
		t.Fatalf("get gated slug: %v", err)
	}
	gateBody := readBody(t, gateResp)
	if gateResp.StatusCode == http.StatusFound || gateResp.StatusCode == http.StatusMovedPermanently {
		t.Fatalf("get gated slug status = %d, want password page, not redirect", gateResp.StatusCode)
	}
	if gateResp.StatusCode != http.StatusOK {
		t.Fatalf("get gated slug status = %d, want 200, body = %s", gateResp.StatusCode, gateBody)
	}

	wrong := postForm(t, srv, "/bpwgate", url.Values{"password": {"wrong-pw"}})
	_ = readBody(t, wrong)
	if wrong.StatusCode != http.StatusUnauthorized {
		t.Fatalf("wrong password status = %d, want 401", wrong.StatusCode)
	}
	right := postForm(t, srv, "/bpwgate", url.Values{"password": {"gate-pw"}})
	_ = readBody(t, right)
	if right.StatusCode != http.StatusFound && right.StatusCode != http.StatusMovedPermanently && right.StatusCode != http.StatusSeeOther {
		t.Fatalf("right password status = %d, want redirect", right.StatusCode)
	}
	if loc := right.Header.Get("Location"); loc != "https://a.com/gated" {
		t.Fatalf("right password Location = %q, want https://a.com/gated", loc)
	}
}
