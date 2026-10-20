package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_BurnedAtWithinRequestWindow(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2ba1",
		URL:     "https://example.com/a1",
		Enabled: true,
		Burn:    true,
	})

	t0 := time.Now().UTC()
	rr := doDeep3(t, h, http.MethodGet, "/b2ba1", nil, "")
	t1 := time.Now().UTC()

	if rr.Code != http.StatusFound {
		t.Fatalf("expected 302, got %d", rr.Code)
	}

	got, err := st.GetLinkBySlug("b2ba1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.BurnedAt == nil {
		t.Fatalf("expected BurnedAt non-nil")
	}
	burnedAt := *got.BurnedAt
	if burnedAt.Before(t0.Add(-time.Minute)) || burnedAt.After(t1.Add(time.Minute)) {
		t.Fatalf("BurnedAt %v outside [%v, %v]", burnedAt, t0.Add(-time.Minute), t1.Add(time.Minute))
	}
	if !strings.HasSuffix(burnedAt.Format(time.RFC3339), "Z") {
		t.Fatalf("BurnedAt not UTC-stored: %v loc=%v", burnedAt, burnedAt.Location())
	}
}

func TestBurnR2_BurnedAtNilBeforeConsume(t *testing.T) {
	st, _ := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2ba2",
		URL:     "https://example.com/a2",
		Enabled: true,
		Burn:    true,
	})

	got, err := st.GetLinkBySlug("b2ba2")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if got.BurnedAt != nil {
		t.Fatalf("expected BurnedAt nil before consume, got %v", *got.BurnedAt)
	}
}

func TestBurnR2_ListShowsBurnedDisabled(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2ba3",
		URL:     "https://example.com/a3",
		Enabled: true,
		Burn:    true,
	})

	rr := doDeep3(t, h, http.MethodGet, "/b2ba3", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("first GET expected 302, got %d", rr.Code)
	}

	lr := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if lr.Code != http.StatusOK {
		t.Fatalf("list expected 200, got %d", lr.Code)
	}
	var payload map[string]any
	if err := json.Unmarshal(lr.Body.Bytes(), &payload); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	items, ok := payload["items"].([]any)
	if !ok {
		t.Fatalf("items not []any: %T", payload["items"])
	}
	found := false
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if m["slug"] == "b2ba3" {
			found = true
			if m["enabled"] != false {
				t.Fatalf("expected enabled false, got %v", m["enabled"])
			}
			break
		}
	}
	if !found {
		t.Fatalf("slug b2ba3 not found in items")
	}
}

func TestBurnR2_ListShowsRemainingOneBeforeBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2ba3",
		URL:     "https://example.com/a3",
		Enabled: true,
		Burn:    true,
	})

	rr := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if rr.Code != http.StatusOK {
		t.Fatalf("list expected 200, got %d", rr.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items not []any: %T", body["items"])
	}
	found := false
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if m["slug"] == "b2ba3" {
			found = true
			got, ok := m["remaining"].(float64)
			if !ok {
				t.Fatalf("remaining not float64: %T", m["remaining"])
			}
			if got != float64(1) {
				t.Fatalf("expected remaining 1, got %v", got)
			}
			break
		}
	}
	if !found {
		t.Fatalf("slug b2ba3 not found in items")
	}
}

func TestBurnR2_ListShowsRemainingZeroAfterBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2ba3",
		URL:     "https://example.com/a3",
		Enabled: true,
		Burn:    true,
	})

	rr := doDeep3(t, h, http.MethodGet, "/b2ba3", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("burn GET expected 302, got %d", rr.Code)
	}

	lr := doDeep3(t, h, http.MethodGet, "/api/links", nil, "")
	if lr.Code != http.StatusOK {
		t.Fatalf("list expected 200, got %d", lr.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(lr.Body.Bytes(), &body); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("items not []any: %T", body["items"])
	}
	found := false
	for _, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			continue
		}
		if m["slug"] == "b2ba3" {
			found = true
			got, ok := m["remaining"].(float64)
			if !ok {
				t.Fatalf("remaining not float64: %T", m["remaining"])
			}
			if got != float64(0) {
				t.Fatalf("expected remaining 0, got %v", got)
			}
			break
		}
	}
	if !found {
		t.Fatalf("slug b2ba3 not found in items")
	}
}