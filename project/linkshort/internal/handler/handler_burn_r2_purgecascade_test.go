package handler

import (
"errors"
"net/http"
"strings"
"testing"

"github.com/Wanfeng1028/muse/linkshort/internal/model"
"github.com/Wanfeng1028/muse/linkshort/internal/store"
)

func TestBurnR2_PurgeAfterBurnDeletesRow(t *testing.T) {
st, h := newDeep3Router(t)
id := mkLinkDeep3(t, st, &model.Link{Slug: "b2pg1", URL: "https://example.com/g1", Enabled: true, Burn: true, PurgeAfterBurn: true})
rr := doDeep3(t, h, http.MethodGet, "/b2pg1", nil, "")
if rr.Code != http.StatusFound {
t.Fatalf("first GET status = %d, want %d", rr.Code, http.StatusFound)
}
_, err := st.GetLinkBySlug("b2pg1")
if !errors.Is(err, store.ErrNotFound) {
t.Fatalf("GetLinkBySlug err = %v, want ErrNotFound", err)
}
_, err = st.GetLink(id)
if !errors.Is(err, store.ErrNotFound) {
t.Fatalf("GetLink err = %v, want ErrNotFound", err)
}
}

func TestBurnR2_PurgeAfterBurnCascadesVisits(t *testing.T) {
st, h := newDeep3Router(t)
id := mkLinkDeep3(t, st, &model.Link{Slug: "b2pg1", URL: "https://example.com/g1", Enabled: true, Burn: true, PurgeAfterBurn: true})
rr := doDeep3(t, h, http.MethodGet, "/b2pg1", nil, "")
if rr.Code != http.StatusFound {
t.Fatalf("GET status = %d, want %d", rr.Code, http.StatusFound)
}
stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks err = %v", err)
}
var sum int64
for _, s := range stats {
sum += s.Clicks
}
if sum != 0 {
t.Fatalf("sum clicks = %d, want 0", sum)
}
}

func TestBurnR2_PurgeAfterBurnSecondGet404(t *testing.T) {
st, h := newDeep3Router(t)
mkLinkDeep3(t, st, &model.Link{Slug: "b2pg1", URL: "https://example.com/g1", Enabled: true, Burn: true, PurgeAfterBurn: true})
rr := doDeep3(t, h, http.MethodGet, "/b2pg1", nil, "")
if rr.Code != http.StatusFound {
t.Fatalf("first GET status = %d, want %d", rr.Code, http.StatusFound)
}
rr = doDeep3(t, h, http.MethodGet, "/b2pg1", nil, "")
if rr.Code != http.StatusNotFound {
t.Fatalf("second GET status = %d, want %d", rr.Code, http.StatusNotFound)
}
if !strings.Contains(rr.Body.String(), "短链不存在") {
t.Fatalf("body = %q, want contains %q", rr.Body.String(), "短链不存在")
}
}

func TestBurnR2_NoPurgeKeepsVisits(t *testing.T) {
st, h := newDeep3Router(t)
id := mkLinkDeep3(t, st, &model.Link{Slug: "b2pg2", URL: "https://example.com/g2", Enabled: true, Burn: true, PurgeAfterBurn: false})
rr := doDeep3(t, h, http.MethodGet, "/b2pg2", nil, "")
if rr.Code != http.StatusFound {
t.Fatalf("first GET status = %d, want %d", rr.Code, http.StatusFound)
}
stats, err := st.LinkDailyClicks(id, 7)
if err != nil {
t.Fatalf("LinkDailyClicks err = %v", err)
}
var sum int64
for _, s := range stats {
sum += s.Clicks
}
if sum != 1 {
t.Fatalf("sum clicks = %d, want 1", sum)
}
rr = doDeep3(t, h, http.MethodGet, "/b2pg2", nil, "")
if rr.Code != http.StatusGone {
t.Fatalf("second GET status = %d, want %d", rr.Code, http.StatusGone)
}
if !strings.Contains(rr.Body.String(), "链接已阅销毁") {
t.Fatalf("body = %q, want contains %q", rr.Body.String(), "链接已阅销毁")
}
}