package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurn2_CombinedBurnWinsOverMaxVisits(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(3)
	mkLinkDeep3(t, st, &model.Link{
		Slug:          "burn2mv",
		URL:           "https://example.com/mv",
		Enabled:       true,
		Burn:          true,
		MaxVisits:     &mv,
		PurgeAfterBurn: false,
	})

	rec := doDeep3(t, h, http.MethodGet, "/burn2mv", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("first visit: want 302, got %d", rec.Code)
	}
	if loc := rec.Header().Get("Location"); loc != "https://example.com/mv" {
		t.Fatalf("first visit: want Location https://example.com/mv, got %q", loc)
	}

	link, err := st.GetLinkBySlug("burn2mv")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Enabled {
		t.Fatalf("expected Enabled=false after burn, got true (max_visits branch may have been taken)")
	}

	rec2 := doDeep3(t, h, http.MethodGet, "/burn2mv", nil, "")
	if rec2.Code != http.StatusGone {
		t.Fatalf("second visit: want 410, got %d", rec2.Code)
	}
	body := rec2.Body.String()
	if !strings.Contains(body, "链接已阅销毁") {
		t.Fatalf("second visit body missing burn message, got %q", body)
	}
	if strings.Contains(body, "链接已达访问上限") {
		t.Fatalf("second visit body contains max_visits message, got %q", body)
	}
}

func TestBurn2_TryBurnLostAfterLoad(t *testing.T) {
	st, _ := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{
		Slug:           "burn2lost",
		URL:            "https://example.com/lost",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: false,
	})

	burned, err := st.TryBurn(id)
	if err != nil {
		t.Fatalf("preemptive TryBurn: %v", err)
	}
	if !burned {
		t.Fatalf("preemptive TryBurn: want true, got false")
	}

	link := &model.Link{
		ID:             id,
		URL:            "https://example.com/lost",
		Enabled:        true,
		Burn:           true,
		PurgeAfterBurn: false,
	}

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/burn2lost", nil)
	finishRedirect(rec, req, link, st, &config.Config{})

	if rec.Code != http.StatusGone {
		t.Fatalf("want 410, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "链接已阅销毁") {
		t.Fatalf("body missing burn message, got %q", rec.Body.String())
	}

	row, err := st.GetLinkBySlug("burn2lost")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if row.Clicks != 0 {
		t.Fatalf("want Clicks=0, got %d", row.Clicks)
	}
}
