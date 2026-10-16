package geo

import (
	"testing"
)

func TestNormalizeIPRejectsNonPublic(t *testing.T) {
	cases := []string{
		"10.0.0.1",
		"192.168.1.1",
		"172.16.5.4",
		"127.0.0.1",
		"::1",
		"fc00::1",
		"",
		"not-an-ip",
		"999.1.1.1",
		"1.2.3.4.5",
		" ",
	}
	for _, c := range cases {
		if _, ok := normalizeIP(c); ok {
			t.Fatalf("normalizeIP(%q) 应为 false", c)
		}
	}
}

func TestStaticResolverHitAndMiss(t *testing.T) {
	r := NewStatic(map[string]Location{
		"8.8.8.8": {CountryCode: "US", CountryName: "美国", Province: "加利福尼亚"},
	})
	got := r.Lookup("8.8.8.8")
	want := Location{CountryCode: "US", CountryName: "美国", Province: "加利福尼亚"}
	if got != want {
		t.Fatalf("命中返回 %+v，期望 %+v", got, want)
	}
	if got := r.Lookup("1.1.1.1"); got != Unknown {
		t.Fatalf("未命中应返回 Unknown，实际 %+v", got)
	}
	for _, bad := range []string{"", "not-an-ip", "10.0.0.1", "127.0.0.1", " "} {
		if got := r.Lookup(bad); got != Unknown {
			t.Fatalf("非法输入 %q 应返回 Unknown，实际 %+v", bad, got)
		}
	}
}

func TestOpenInvalidPath(t *testing.T) {
	if _, err := Open("/nonexistent/path.mmdb"); err == nil {
		t.Fatal("Open(不存在的路径) 应返回错误")
	}
	if _, err := Open(""); err == nil {
		t.Fatal("Open(\"\") 应返回错误")
	}
}

func TestFromEnvWithoutPath(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()
	r := FromEnv()
	if r == nil {
		t.Fatal("FromEnv 不应返回 nil")
	}
	if got := r.Lookup("203.0.113.7"); got != Unknown {
		t.Fatalf("未配置 mmdb 且无内置表命中时应返回 Unknown，实际 %+v", got)
	}
	if got := r.Lookup("8.8.8.8"); got == Unknown {
		t.Skip("china.go 未注入内置表时跳过")
	} else if got.CountryCode != "US" {
		t.Fatalf("8.8.8.8 期望 CountryCode=US，实际 %+v", got)
	}
}

func TestFromEnvWithBadPath(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "/nonexistent/path.mmdb")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()
	r := FromEnv()
	if r == nil {
		t.Fatal("FromEnv 不应返回 nil")
	}
	if got := r.Lookup("203.0.113.7"); got != Unknown {
		t.Fatalf("mmdb 路径无效时应降级，203.0.113.7 应返回 Unknown，实际 %+v", got)
	}
}
