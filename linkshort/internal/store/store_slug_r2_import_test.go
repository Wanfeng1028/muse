package store

import (
	"strings"
	"testing"
)

func TestStoreSlugR2_ImportMixed(t *testing.T) {
	s := newTestStore(t)
	csv := `slug,url,title,enabled,expires_at,max_visits,burn
b2im1,https://example.com/1,好链,true,,,false
b2im2,ftp://example.com/2,坏URL,true,,,false
b2im3,,空URL,true,,,false
b2im1,https://example.com/dup,重复slug,true,,,false
slug with space,https://example.com/5,坏slug,true,,,false
b2im6,https://example.com/6,限次,badbool,,,false
只有 1 行
b2im8,https://example.com/8,burn限次冲突,true,,5,true
`
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csv))
	if imported != 1 {
		t.Fatalf("imported = %d, want 1", imported)
	}
	if skipped != 7 {
		t.Fatalf("skipped = %d, want 7", skipped)
	}
	if len(errs) != 7 {
		t.Fatalf("len(errs) = %d, want 7: %v", len(errs), errs)
	}
	wants := []string{"invalid enabled", "burn cannot combine", "expected at least 2 columns", "empty url"}
	for _, want := range wants {
		found := false
		for _, e := range errs {
			if strings.Contains(e, want) {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("errs missing substring %q: %v", want, errs)
		}
	}
}

func TestStoreSlugR2_ImportHeaderCaseInsensitive(t *testing.T) {
	s := newTestStore(t)
	csv := `SLUG,URL
b2imh1,https://example.com/h1
`
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csv))
	if imported != 1 {
		t.Fatalf("imported = %d, want 1 (errs=%v)", imported, errs)
	}
	if skipped != 0 {
		t.Fatalf("skipped = %d, want 0 (errs=%v)", skipped, errs)
	}
	if len(errs) != 0 {
		t.Fatalf("len(errs) = %d, want 0: %v", len(errs), errs)
	}
}

func TestStoreSlugR2_ImportNoHeader(t *testing.T) {
	s := newTestStore(t)
	csv := `b2imnh1,https://example.com/nh1
b2imnh2,https://example.com/nh2
`
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csv))
	if imported != 2 {
		t.Fatalf("imported = %d, want 2 (errs=%v)", imported, errs)
	}
	if skipped != 0 {
		t.Fatalf("skipped = %d, want 0 (errs=%v)", skipped, errs)
	}
	if len(errs) != 0 {
		t.Fatalf("len(errs) = %d, want 0: %v", len(errs), errs)
	}
}