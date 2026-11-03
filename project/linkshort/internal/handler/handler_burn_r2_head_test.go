package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_HeadReturns405(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2head1",
		URL:     "https://example.com/h1",
		Enabled: true,
		Burn:    true,
	})
	rr := doDeep3(t, h, http.MethodHead, "/b2head1", nil, "")
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("HEAD on burn link: got %d, want %d (chi rejects HEAD since only GET/POST registered)", rr.Code, http.StatusMethodNotAllowed)
	}
}

func TestBurnR2_HeadDoesNotConsumeBurn(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2head1",
		URL:     "https://example.com/h1",
		Enabled: true,
		Burn:    true,
	})

	rrHead := doDeep3(t, h, http.MethodHead, "/b2head1", nil, "")
	if rrHead.Code != http.StatusMethodNotAllowed {
		t.Fatalf("HEAD: got %d, want %d", rrHead.Code, http.StatusMethodNotAllowed)
	}

	link, err := st.GetLinkBySlug("b2head1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if !link.Enabled {
		t.Fatalf("after HEAD, link.Enabled = false, want true")
	}
	if link.BurnedAt != nil {
		t.Fatalf("after HEAD, link.BurnedAt = %v, want nil", link.BurnedAt)
	}

	rrGet := doDeep3(t, h, http.MethodGet, "/b2head1", nil, "")
	if rrGet.Code != http.StatusFound {
		t.Fatalf("GET after HEAD: got %d, want %d", rrGet.Code, http.StatusFound)
	}
	if loc := rrGet.Header().Get("Location"); loc != "https://example.com/h1" {
		t.Fatalf("GET Location = %q, want %q", loc, "https://example.com/h1")
	}
}

func TestBurnR2_HeadOnNormalLink405(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2head2",
		URL:     "https://example.com/h2",
		Enabled: true,
		Burn:    false,
	})

	rrHead := doDeep3(t, h, http.MethodHead, "/b2head2", nil, "")
	if rrHead.Code != http.StatusMethodNotAllowed {
		t.Fatalf("HEAD on normal link: got %d, want %d", rrHead.Code, http.StatusMethodNotAllowed)
	}

	rrGet := doDeep3(t, h, http.MethodGet, "/b2head2", nil, "")
	if rrGet.Code != http.StatusFound {
		t.Fatalf("GET on normal link: got %d, want %d", rrGet.Code, http.StatusFound)
	}
	if loc := rrGet.Header().Get("Location"); loc != "https://example.com/h2" {
		t.Fatalf("GET Location = %q, want %q", loc, "https://example.com/h2")
	}

	link, err := st.GetLinkBySlug("b2head2")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link.Clicks != 1 {
		t.Fatalf("clicks = %d, want 1 (HEAD must not count)", link.Clicks)
	}
}