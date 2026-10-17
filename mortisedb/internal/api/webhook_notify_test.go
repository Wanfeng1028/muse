package api

import (
	"bytes"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/notify"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

const whSecret = "test-secret-123"

type fakeWebhook struct {
	mu   sync.Mutex
	reqs []whRequest
}

type whRequest struct {
	headers map[string]string
	body    []byte
}

func (f *fakeWebhook) handler(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	hdrs := map[string]string{
		"X-Mortise-Event":       r.Header.Get("X-Mortise-Event"),
		"X-Mortise-Signature":   r.Header.Get("X-Mortise-Signature"),
		"X-Mortise-Delivery-Id": r.Header.Get("X-Mortise-Delivery-Id"),
	}
	f.mu.Lock()
	f.reqs = append(f.reqs, whRequest{headers: hdrs, body: body})
	f.mu.Unlock()
	w.WriteHeader(http.StatusOK)
}

func (f *fakeWebhook) received() []whRequest {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]whRequest, len(f.reqs))
	copy(out, f.reqs)
	return out
}

func whSetup(t *testing.T, conflictMode string) (*store.Store, *config.Config, http.Handler, *fakeWebhook) {
	t.Helper()
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	fake := &fakeWebhook{}
	ts := httptest.NewServer(http.HandlerFunc(fake.handler))
	t.Cleanup(ts.Close)

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Table: "t_wh_main", PrimaryKey: "id"},
		{Name: "s2", Type: "csv", Table: "t_wh_main", PrimaryKey: "id"},
	}
	cfg.Sync.Conflict = conflictMode
	cfg.Notify = config.NotifyConfig{
		ConflictWebhookURL:        ts.URL + "/hook",
		ConflictWebhookSecret:     whSecret,
		ConflictWebhookTimeout:    "2s",
		ConflictWebhookMaxRetries: 1,
	}

	srv := NewServer(st, cfg, log.New(io.Discard, "info"))
	return st, cfg, srv, fake
}

func postImportCSV(t *testing.T, srv http.Handler, route, source, filename, content string) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	fw, err := mw.CreateFormFile("file", filename)
	if err != nil {
		t.Fatalf("CreateFormFile: %v", err)
	}
	if _, err := fw.Write([]byte(content)); err != nil {
		t.Fatalf("write file: %v", err)
	}
	if route == "/api/import/csv" {
		if err := mw.WriteField("source", source); err != nil {
			t.Fatalf("WriteField: %v", err)
		}
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("mw.Close: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, route, &buf)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	rec := httptest.NewRecorder()
	srv.ServeHTTP(rec, req)
	return rec
}

func waitFor(t *testing.T, cond func() bool, msg string) {
	t.Helper()
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		if cond() {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("waitFor timeout: %s", msg)
}

func findEvent(reqs []whRequest, event string) (whRequest, bool) {
	for _, r := range reqs {
		if r.headers["X-Mortise-Event"] == event {
			return r, true
		}
	}
	return whRequest{}, false
}

func TestImportConflictWebhookDelivered(t *testing.T) {
	_, _, srv, fake := whSetup(t, "manual")

	rec := postImportCSV(t, srv, "/api/sources/s1/import-csv", "", "s1.csv", "id,name\n1,alice\n")
	if rec.Code != http.StatusOK {
		t.Fatalf("s1 import code = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}

	rec = postImportCSV(t, srv, "/api/sources/s2/import-csv", "", "s2.csv", "id,name\n1,bob\n")
	if rec.Code != http.StatusConflict {
		t.Fatalf("s2 import code = %d, want 409, body=%s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), `"status":"pending"`) {
		t.Fatalf("s2 import body missing pending: %s", rec.Body.String())
	}

	var got whRequest
	waitFor(t, func() bool {
		r, ok := findEvent(fake.received(), notify.EventPending)
		if ok {
			got = r
		}
		return ok
	}, "no conflict.pending webhook received")

	if got.headers["X-Mortise-Event"] != notify.EventPending {
		t.Fatalf("event header = %q, want %q", got.headers["X-Mortise-Event"], notify.EventPending)
	}
	wantSig := "sha256=" + notify.Sign(whSecret, got.body)
	if got.headers["X-Mortise-Signature"] != wantSig {
		t.Fatalf("signature = %q, want %q", got.headers["X-Mortise-Signature"], wantSig)
	}
	if got.headers["X-Mortise-Delivery-Id"] == "" {
		t.Fatalf("delivery id header is empty")
	}

	var payload struct {
		Event      string `json:"event"`
		DeliveryID string `json:"delivery_id"`
		Conflict   struct {
			PK        string `json:"pk"`
			TableName string `json:"table_name"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(got.body, &payload); err != nil {
		t.Fatalf("unmarshal body: %v, body=%s", err, string(got.body))
	}
	if payload.Event != notify.EventPending {
		t.Fatalf("body event = %q, want %q", payload.Event, notify.EventPending)
	}
	if payload.DeliveryID != got.headers["X-Mortise-Delivery-Id"] {
		t.Fatalf("body delivery_id = %q, header = %q", payload.DeliveryID, got.headers["X-Mortise-Delivery-Id"])
	}
	if payload.Conflict.PK != "1" {
		t.Fatalf("conflict.pk = %q, want 1", payload.Conflict.PK)
	}
	if payload.Conflict.TableName != "t_wh_main" {
		t.Fatalf("conflict.table_name = %q, want t_wh_main", payload.Conflict.TableName)
	}
}

func TestImportCSVNewConflictWebhookDelivered(t *testing.T) {
	_, _, srv, fake := whSetup(t, "manual")

	rec := postImportCSV(t, srv, "/api/import/csv", "s1", "s1.csv", "id,name\n1,alice\n")
	if rec.Code != http.StatusOK {
		t.Fatalf("s1 import code = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}

	rec = postImportCSV(t, srv, "/api/import/csv", "s2", "s2.csv", "id,name\n1,bob\n")
	if rec.Code != http.StatusConflict {
		t.Fatalf("s2 import code = %d, want 409, body=%s", rec.Code, rec.Body.String())
	}

	var got whRequest
	waitFor(t, func() bool {
		r, ok := findEvent(fake.received(), notify.EventPending)
		if ok {
			got = r
		}
		return ok
	}, "no conflict.pending webhook received via /api/import/csv")

	wantSig := "sha256=" + notify.Sign(whSecret, got.body)
	if got.headers["X-Mortise-Signature"] != wantSig {
		t.Fatalf("signature = %q, want %q", got.headers["X-Mortise-Signature"], wantSig)
	}
}

func TestWebhookFailureDoesNotBlockImport(t *testing.T) {
	st, err := store.Open(":memory:")
	if err != nil {
		t.Fatalf("store.Open: %v", err)
	}
	if err := st.Migrate(); err != nil {
		t.Fatalf("Migrate: %v", err)
	}

	cfg := config.DefaultConfig()
	cfg.Sources = []config.SourceConfig{
		{Name: "s1", Type: "csv", Table: "t_wh_main", PrimaryKey: "id"},
		{Name: "s2", Type: "csv", Table: "t_wh_main", PrimaryKey: "id"},
	}
	cfg.Sync.Conflict = "manual"
	cfg.Notify = config.NotifyConfig{
		ConflictWebhookURL:        "http://127.0.0.1:9/hook",
		ConflictWebhookSecret:     whSecret,
		ConflictWebhookTimeout:    "2s",
		ConflictWebhookMaxRetries: 1,
	}

	srv := NewServer(st, cfg, log.New(io.Discard, "info"))

	rec := postImportCSV(t, srv, "/api/sources/s1/import-csv", "", "s1.csv", "id,name\n1,alice\n")
	if rec.Code != http.StatusOK {
		t.Fatalf("s1 import code = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}

	rec = postImportCSV(t, srv, "/api/sources/s2/import-csv", "", "s2.csv", "id,name\n1,bob\n")
	if rec.Code != http.StatusConflict {
		t.Fatalf("s2 import code = %d, want 409, body=%s", rec.Code, rec.Body.String())
	}

	waitFor(t, func() bool {
		return strings.Contains(metrics.Default().Render(), `status="failed"`)
	}, `metrics missing status="failed"`)
}

func TestResolveConflictWebhookDelivered(t *testing.T) {
	_, _, srv, fake := whSetup(t, "manual")

	rec := postImportCSV(t, srv, "/api/sources/s1/import-csv", "", "s1.csv", "id,name\n1,alice\n")
	if rec.Code != http.StatusOK {
		t.Fatalf("s1 import code = %d, want 200, body=%s", rec.Code, rec.Body.String())
	}
	rec = postImportCSV(t, srv, "/api/sources/s2/import-csv", "", "s2.csv", "id,name\n1,bob\n")
	if rec.Code != http.StatusConflict {
		t.Fatalf("s2 import code = %d, want 409, body=%s", rec.Code, rec.Body.String())
	}

	listReq := httptest.NewRequest(http.MethodGet, "/api/conflicts?status=pending", nil)
	listRec := httptest.NewRecorder()
	srv.ServeHTTP(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list conflicts code = %d, want 200, body=%s", listRec.Code, listRec.Body.String())
	}

	var conflicts []struct {
		ID int64 `json:"id"`
	}
	if err := json.Unmarshal(listRec.Body.Bytes(), &conflicts); err != nil {
		t.Fatalf("unmarshal conflicts: %v, body=%s", err, listRec.Body.String())
	}
	if len(conflicts) == 0 || conflicts[0].ID == 0 {
		t.Fatalf("no pending conflict id found: %s", listRec.Body.String())
	}
	id := strconv.FormatInt(conflicts[0].ID, 10)

	resolveBody := `{"row_json":"{\"id\":\"1\",\"name\":\"bob\"}","table":"t_wh_main","pk_col":"id","pk":"1"}`
	resolveReq := httptest.NewRequest(http.MethodPost, "/api/conflicts/"+id+"/resolve", strings.NewReader(resolveBody))
	resolveReq.Header.Set("Content-Type", "application/json")
	resolveRec := httptest.NewRecorder()
	srv.ServeHTTP(resolveRec, resolveReq)
	if resolveRec.Code != http.StatusOK {
		t.Fatalf("resolve code = %d, want 200, body=%s", resolveRec.Code, resolveRec.Body.String())
	}

	var got whRequest
	waitFor(t, func() bool {
		r, ok := findEvent(fake.received(), notify.EventResolved)
		if ok {
			got = r
		}
		return ok
	}, "no conflict.resolved webhook received")

	wantSig := "sha256=" + notify.Sign(whSecret, got.body)
	if got.headers["X-Mortise-Signature"] != wantSig {
		t.Fatalf("signature = %q, want %q", got.headers["X-Mortise-Signature"], wantSig)
	}

	var payload struct {
		Event    string `json:"event"`
		Conflict struct {
			Status string `json:"status"`
		} `json:"conflict"`
	}
	if err := json.Unmarshal(got.body, &payload); err != nil {
		t.Fatalf("unmarshal body: %v, body=%s", err, string(got.body))
	}
	if payload.Event != notify.EventResolved {
		t.Fatalf("body event = %q, want %q", payload.Event, notify.EventResolved)
	}
	if payload.Conflict.Status != "resolved" {
		t.Fatalf("conflict.status = %q, want resolved", payload.Conflict.Status)
	}
}
