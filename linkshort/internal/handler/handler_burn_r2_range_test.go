package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/db"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestBurnR2_RangeHeaderIgnoredOnBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2range1",
		URL:     "https://example.com/r1",
		Enabled: true,
		Burn:    true,
	})
	rr := doDeep3(t, h, http.MethodGet, "/b2range1", map[string]string{"Range": "bytes=0-99"}, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("first GET status = %d, want 302", rr.Code)
	}
	if loc := rr.Header().Get("Location"); loc != "https://example.com/r1" {
		t.Fatalf("Location = %q, want %q", loc, "https://example.com/r1")
	}
}

func TestBurnR2_RangeSecondGet410(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2range1",
		URL:     "https://example.com/r1",
		Enabled: true,
		Burn:    true,
	})
	first := doDeep3(t, h, http.MethodGet, "/b2range1", map[string]string{"Range": "bytes=0-99"}, "")
	if first.Code != http.StatusFound {
		t.Fatalf("first GET status = %d, want 302", first.Code)
	}
	second := doDeep3(t, h, http.MethodGet, "/b2range1", map[string]string{"Range": "bytes=0-99"}, "")
	if second.Code != http.StatusGone {
		t.Fatalf("second GET status = %d, want 410", second.Code)
	}
	if !strings.Contains(second.Body.String(), "链接已阅销毁") {
		t.Fatalf("second GET body = %q, want contains %q", second.Body.String(), "链接已阅销毁")
	}
}

func TestBurnR2_RangeOnNormalLinkNoPartial(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2range2",
		URL:     "https://example.com/normal",
		Enabled: true,
		Burn:    false,
	})
	rr := doDeep3(t, h, http.MethodGet, "/b2range2", map[string]string{"Range": "bytes=0-99"}, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("GET status = %d, want 302", rr.Code)
	}
	if rr.Code == http.StatusPartialContent {
		t.Fatalf("GET status = 206, want not 206")
	}
	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 1 {
		t.Fatalf("Clicks = %d, want 1", link.Clicks)
	}
}

func TestBurnR2_IfRangeHeaderOnExpired410(t *testing.T) {
	st, h := newDeep3Router(t)
	past := time.Now().Add(-time.Hour)
	mkLinkDeep3(t, st, &model.Link{
		Slug:      "b2range3",
		URL:       "https://example.com/expired",
		Enabled:   true,
		Burn:      true,
		ExpiresAt: &past,
	})
	rr := doDeep3(t, h, http.MethodGet, "/b2range3", map[string]string{"Range": "bytes=0-99"}, "")
	if rr.Code != http.StatusGone {
		t.Fatalf("GET status = %d, want 410", rr.Code)
	}
	if !strings.Contains(rr.Body.String(), "链接已过期") {
		t.Fatalf("body = %q, want contains %q", rr.Body.String(), "链接已过期")
	}
	link, err := st.GetLinkBySlug("b2range3")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if !link.Enabled {
		t.Fatalf("Enabled = false, want true (expired check precedes burn)")
	}
}

var _ = httptest.NewRequest
var _ = config.Config{}
var _ = db.Open
var _ = store.New
