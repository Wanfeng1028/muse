package handler

import (
	"net/http"
	"strconv"
	"strings"
	"testing"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
)

func TestLimitR2_PatchMaxVisitsRetroactive(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lm1", URL: "https://example.com/m1", Enabled: true})

	for i := 0; i < 5; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/"+"b2lm1", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("get %d: got %d want %d", i, rec.Code, http.StatusFound)
		}
	}

	rec := doDeep3(t, h, http.MethodPatch, "/api/links/"+strconv.FormatInt(id, 10), nil, `{"max_visits":3}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("patch: got %d want %d", rec.Code, http.StatusOK)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2lm1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("get after patch: got %d want %d", rec.Code, http.StatusGone)
	}
	if !strings.Contains(rec.Body.String(), "链接已达访问上限") {
		t.Fatalf("body: got %q want contains %q", rec.Body.String(), "链接已达访问上限")
	}
}

func TestLimitR2_PatchMaxVisitsNullRestores(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lm1", URL: "https://example.com/m1", Enabled: true})

	for i := 0; i < 5; i++ {
		rec := doDeep3(t, h, http.MethodGet, "/b2lm1", nil, "")
		if rec.Code != http.StatusFound {
			t.Fatalf("get %d: got %d want %d", i, rec.Code, http.StatusFound)
		}
	}

	rec := doDeep3(t, h, http.MethodPatch, "/api/links/"+strconv.FormatInt(id, 10), nil, `{"max_visits":3}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("patch set: got %d want %d", rec.Code, http.StatusOK)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2lm1", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("get exhausted: got %d want %d", rec.Code, http.StatusGone)
	}

	rec = doDeep3(t, h, http.MethodPatch, "/api/links/"+strconv.FormatInt(id, 10), nil, `{"max_visits":null}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("patch null: got %d want %d", rec.Code, http.StatusOK)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.MaxVisits != nil {
		t.Fatalf("MaxVisits: got %v want nil", *link.MaxVisits)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2lm1", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("get restored: got %d want %d", rec.Code, http.StatusFound)
	}

	link, err = st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink after: %v", err)
	}
	if link.Clicks != 6 {
		t.Fatalf("Clicks: got %d want %d", link.Clicks, 6)
	}
}

func TestLimitR2_PatchMaxVisitsRaiseResumes(t *testing.T) {
	st, h := newDeep3Router(t)
	mv := int64(2)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lm2", URL: "https://example.com/m2", Enabled: true, MaxVisits: &mv})

	rec := doDeep3(t, h, http.MethodGet, "/b2lm2", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("get 1: got %d want %d", rec.Code, http.StatusFound)
	}
	rec = doDeep3(t, h, http.MethodGet, "/b2lm2", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("get 2: got %d want %d", rec.Code, http.StatusFound)
	}
	rec = doDeep3(t, h, http.MethodGet, "/b2lm2", nil, "")
	if rec.Code != http.StatusGone {
		t.Fatalf("get 3: got %d want %d", rec.Code, http.StatusGone)
	}

	rec = doDeep3(t, h, http.MethodPatch, "/api/links/"+strconv.FormatInt(id, 10), nil, `{"max_visits":5}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("patch raise: got %d want %d", rec.Code, http.StatusOK)
	}

	rec = doDeep3(t, h, http.MethodGet, "/b2lm2", nil, "")
	if rec.Code != http.StatusFound {
		t.Fatalf("get resumed: got %d want %d", rec.Code, http.StatusFound)
	}

	link, err := st.GetLink(id)
	if err != nil {
		t.Fatalf("GetLink: %v", err)
	}
	if link.Clicks != 3 {
		t.Fatalf("Clicks: got %d want %d", link.Clicks, 3)
	}
}

func TestLimitR2_PatchMaxVisitsZero400(t *testing.T) {
	st, h := newDeep3Router(t)
	id := mkLinkDeep3(t, st, &model.Link{Slug: "b2lm3", URL: "https://example.com/m3", Enabled: true})

	rec := doDeep3(t, h, http.MethodPatch, "/api/links/"+strconv.FormatInt(id, 10), nil, `{"max_visits":0}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("patch zero: got %d want %d", rec.Code, http.StatusBadRequest)
	}
}
