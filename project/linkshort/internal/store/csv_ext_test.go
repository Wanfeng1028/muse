package store

import (
	"strings"
	"testing"
)

// TestImportCSV_WithNewColumns 验证带新列（max_visits、burn）的 7 列 CSV 能正确导入。
func TestImportCSV_WithNewColumns(t *testing.T) {
	s := newTestStore(t)

	csvData := "slug,url,title,enabled,expires_at,max_visits,burn\n" +
		"limited,https://example.com/1,限次链,true,,5,false\n" +
		"burnme,https://example.com/2,burn链,true,,1,true\n" +
		"plain,https://example.com/3,普通链,true,,,\n"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 3 {
		t.Fatalf("imported = %d, want 3; errs=%v", imported, errs)
	}
	if skipped != 0 {
		t.Fatalf("skipped = %d, want 0; errs=%v", skipped, errs)
	}

	l1, err := s.GetLinkBySlug("limited")
	if err != nil {
		t.Fatalf("GetLink(limited): %v", err)
	}
	if l1.MaxVisits == nil || *l1.MaxVisits != 5 {
		t.Fatalf("limited MaxVisits = %v, want 5", l1.MaxVisits)
	}
	if l1.Burn {
		t.Fatalf("limited Burn = true, want false")
	}

	l2, err := s.GetLinkBySlug("burnme")
	if err != nil {
		t.Fatalf("GetLink(burnme): %v", err)
	}
	if !l2.Burn {
		t.Fatalf("burnme Burn = false, want true")
	}
	if l2.MaxVisits == nil || *l2.MaxVisits != 1 {
		t.Fatalf("burnme MaxVisits = %v, want 1", l2.MaxVisits)
	}

	l3, err := s.GetLinkBySlug("plain")
	if err != nil {
		t.Fatalf("GetLink(plain): %v", err)
	}
	if l3.MaxVisits != nil {
		t.Fatalf("plain MaxVisits = %v, want nil", l3.MaxVisits)
	}
	if l3.Burn {
		t.Fatalf("plain Burn = true, want false")
	}
}

// TestImportCSV_OldFormatCompat 验证旧 5 列 CSV（无新列）仍可导入，缺失列按默认值处理。
func TestImportCSV_OldFormatCompat(t *testing.T) {
	s := newTestStore(t)

	csvData := "slug,url,title,enabled,expires_at\n" +
		"old1,https://example.com/a,老链1,true,\n" +
		"old2,https://example.com/b,老链2,false,"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 2 {
		t.Fatalf("imported = %d, want 2; errs=%v", imported, errs)
	}
	if skipped != 0 {
		t.Fatalf("skipped = %d, want 0; errs=%v", skipped, errs)
	}

	for _, slug := range []string{"old1", "old2"} {
		l, err := s.GetLinkBySlug(slug)
		if err != nil {
			t.Fatalf("GetLink(%s): %v", slug, err)
		}
		if l.MaxVisits != nil {
			t.Fatalf("%s MaxVisits = %v, want nil", slug, l.MaxVisits)
		}
		if l.Burn {
			t.Fatalf("%s Burn = true, want false", slug)
		}
	}
}

// TestImportCSV_InvalidCombos 验证非法 max_visits 与 burn 组合被跳过并记录错误。
func TestImportCSV_InvalidCombos(t *testing.T) {
	s := newTestStore(t)

	csvData := "slug,url,title,enabled,expires_at,max_visits,burn\n" +
		"badcombo,https://example.com/x,x,true,,5,true\n" +
		"zero,https://example.com/y,y,true,,0,false\n" +
		"abc,https://example.com/z,z,true,,abc,false\n"
	imported, skipped, errs := s.ImportCSV(strings.NewReader(csvData))
	if imported != 0 {
		t.Fatalf("imported = %d, want 0; errs=%v", imported, errs)
	}
	if skipped != 3 {
		t.Fatalf("skipped = %d, want 3; errs=%v", skipped, errs)
	}
	if len(errs) == 0 {
		t.Fatalf("errs 为空, 期望有错误")
	}
}

// TestExportCSV_RoundTrip 验证导出再导入后关键字段一致。
func TestExportCSV_RoundTrip(t *testing.T) {
	s1 := newTestStore(t)

	mv := int64(3)
	if _, err := s1.CreateLinkEx("rt-plain", "https://example.com/p", "普通", nil, nil, false, false); err != nil {
		t.Fatalf("CreateLinkEx(plain): %v", err)
	}
	if _, err := s1.CreateLinkEx("rt-limited", "https://example.com/l", "限次", nil, &mv, false, false); err != nil {
		t.Fatalf("CreateLinkEx(limited): %v", err)
	}
	if _, err := s1.CreateLinkEx("rt-burn", "https://example.com/b", "burn", nil, nil, true, false); err != nil {
		t.Fatalf("CreateLinkEx(burn): %v", err)
	}

	var buf strings.Builder
	if err := s1.ExportCSV(&buf); err != nil {
		t.Fatalf("ExportCSV: %v", err)
	}

	s2 := newTestStore(t)
	imported, skipped, errs := s2.ImportCSV(strings.NewReader(buf.String()))
	if imported != 3 {
		t.Fatalf("reimport imported = %d, want 3; errs=%v", imported, errs)
	}
	if skipped != 0 {
		t.Fatalf("reimport skipped = %d, want 0; errs=%v", skipped, errs)
	}

	type expect struct {
		url       string
		maxVisits *int64
		burn      bool
	}
	want := map[string]expect{
		"rt-plain":   {url: "https://example.com/p", maxVisits: nil, burn: false},
		"rt-limited": {url: "https://example.com/l", maxVisits: &mv, burn: false},
		"rt-burn":    {url: "https://example.com/b", maxVisits: nil, burn: true},
	}
	for slug, w := range want {
		l, err := s2.GetLinkBySlug(slug)
		if err != nil {
			t.Fatalf("GetLink(%s): %v", slug, err)
		}
		if l.URL != w.url {
			t.Fatalf("%s URL = %q, want %q", slug, l.URL, w.url)
		}
		if (l.MaxVisits == nil) != (w.maxVisits == nil) {
			t.Fatalf("%s MaxVisits = %v, want %v", slug, l.MaxVisits, w.maxVisits)
		}
		if l.MaxVisits != nil && *l.MaxVisits != *w.maxVisits {
			t.Fatalf("%s MaxVisits = %d, want %d", slug, *l.MaxVisits, *w.maxVisits)
		}
		if l.Burn != w.burn {
			t.Fatalf("%s Burn = %v, want %v", slug, l.Burn, w.burn)
		}
	}
}
