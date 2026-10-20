package handler

import (
"bytes"
"encoding/json"
"mime/multipart"
"net/http"
"net/http/httptest"
"strings"
"testing"
)

func TestSlugR2_ImportMixedViaHTTP(t *testing.T) {
st, h := newDeep3Router(t)
_ = st

var buf bytes.Buffer
w := multipart.NewWriter(&buf)
fw, err := w.CreateFormFile("file", "import.csv")
if err != nil {
t.Fatalf("CreateFormFile: %v", err)
}
csvContent := "slug,url\n" +
"b2hi1,https://example.com/1\n" +
"b2hi2,https://example.com/2\n" +
"b2hi3,ftp://x\n" +
"b2hi1,https://example.com/dup\n"
if _, err := fw.Write([]byte(csvContent)); err != nil {
t.Fatalf("write csv: %v", err)
}
if err := w.Close(); err != nil {
t.Fatalf("close writer: %v", err)
}

req := httptest.NewRequest("POST", "/api/import", &buf)
req.Header.Set("Content-Type", w.FormDataContentType())
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)

if rr.Code != http.StatusOK {
t.Fatalf("status = %d, body = %s", rr.Code, rr.Body.String())
}

var payload map[string]any
if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
t.Fatalf("unmarshal: %v, body = %s", err, rr.Body.String())
}

imported, ok := payload["imported"].(float64)
if !ok {
t.Fatalf("imported missing or wrong type: %#v", payload["imported"])
}
if imported != 2 {
t.Fatalf("imported = %v, want 2", imported)
}

skipped, ok := payload["skipped"].(float64)
if !ok {
t.Fatalf("skipped missing or wrong type: %#v", payload["skipped"])
}
if skipped != 2 {
t.Fatalf("skipped = %v, want 2", skipped)
}
}

func TestSlugR2_ImportMissingFile400(t *testing.T) {
_, h := newDeep3Router(t)

req := httptest.NewRequest("POST", "/api/import", nil)
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)

if rr.Code != http.StatusBadRequest {
t.Fatalf("status = %d, want 400, body = %s", rr.Code, rr.Body.String())
}
}

func TestSlugR2_ImportResponseShape(t *testing.T) {
_, h := newDeep3Router(t)

var buf bytes.Buffer
w := multipart.NewWriter(&buf)
fw, err := w.CreateFormFile("file", "import.csv")
if err != nil {
t.Fatalf("CreateFormFile: %v", err)
}
csvContent := "slug,url\n" +
"b2hi1,https://example.com/1\n"
if _, err := fw.Write([]byte(csvContent)); err != nil {
t.Fatalf("write csv: %v", err)
}
if err := w.Close(); err != nil {
t.Fatalf("close writer: %v", err)
}

req := httptest.NewRequest("POST", "/api/import", &buf)
req.Header.Set("Content-Type", w.FormDataContentType())
rr := httptest.NewRecorder()
h.ServeHTTP(rr, req)

if rr.Code != http.StatusOK {
t.Fatalf("status = %d, body = %s", rr.Code, rr.Body.String())
}

var payload map[string]any
if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
t.Fatalf("unmarshal: %v, body = %s", err, rr.Body.String())
}

for _, key := range []string{"imported", "skipped", "errors"} {
if _, ok := payload[key]; !ok {
t.Fatalf("missing key %q in %s", key, rr.Body.String())
}
}

errsVal, ok := payload["errors"].([]any)
if !ok {
t.Fatalf("errors wrong type or null: %#v", payload["errors"])
}
if len(errsVal) != 0 {
t.Fatalf("errors = %#v, want empty array", errsVal)
}

if strings.Contains(rr.Body.String(), "\"errors\":null") {
t.Fatalf("errors serialized as null: %s", rr.Body.String())
}
}