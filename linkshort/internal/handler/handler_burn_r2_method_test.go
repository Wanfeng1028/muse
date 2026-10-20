package handler

import (
	"net/http"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestBurnR2_PutReturns405(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2m1",
		URL:     "https://example.com/m1",
		Enabled: true,
		Burn:    true,
	})
	rr := doDeep3(t, h, http.MethodPut, "/b2m1", nil, "")
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("PUT status = %d, want %d", rr.Code, http.StatusMethodNotAllowed)
	}
}

func TestBurnR2_DeleteReturns405(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2m1",
		URL:     "https://example.com/m1",
		Enabled: true,
		Burn:    true,
	})
	rr := doDeep3(t, h, http.MethodDelete, "/b2m1", nil, "")
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("DELETE status = %d, want %d", rr.Code, http.StatusMethodNotAllowed)
	}
}

func TestBurnR2_PatchMethodReturns405(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2m1",
		URL:     "https://example.com/m1",
		Enabled: true,
		Burn:    true,
	})
	rr := doDeep3(t, h, http.MethodPatch, "/b2m1", nil, "")
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("PATCH status = %d, want %d", rr.Code, http.StatusMethodNotAllowed)
	}
}

func TestBurnR2_WrongMethodsDoNotConsume(t *testing.T) {
	st, h := newDeep3Router(t)
	mkLinkDeep3(t, st, &model.Link{
		Slug:    "b2m1",
		URL:     "https://example.com/m1",
		Enabled: true,
		Burn:    true,
	})

	for _, method := range []string{http.MethodPut, http.MethodDelete, http.MethodPatch} {
		rr := doDeep3(t, h, method, "/b2m1", nil, "")
		if rr.Code != http.StatusMethodNotAllowed {
			t.Fatalf("%s status = %d, want %d", method, rr.Code, http.StatusMethodNotAllowed)
		}
	}

	link, err := st.GetLinkBySlug("b2m1")
	if err != nil {
		t.Fatalf("GetLinkBySlug: %v", err)
	}
	if link == nil {
		t.Fatal("GetLinkBySlug returned nil link")
	}
	if !link.Enabled {
		t.Fatalf("link.Enabled = %v, want true", link.Enabled)
	}
	if link.BurnedAt != nil {
		t.Fatalf("link.BurnedAt = %v, want nil", link.BurnedAt)
	}

	rr := doDeep3(t, h, http.MethodGet, "/b2m1", nil, "")
	if rr.Code != http.StatusFound {
		t.Fatalf("GET status = %d, want %d", rr.Code, http.StatusFound)
	}
	if loc := rr.Header().Get("Location"); loc != "https://example.com/m1" {
		t.Fatalf("Location = %q, want %q", loc, "https://example.com/m1")
	}
}
