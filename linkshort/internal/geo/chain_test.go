package geo

import (
	"sync"
	"testing"
)

// TestLookupRequestTiers 验证内网地址、公网未命中与非法输入的分层判定。
func TestLookupRequestTiers(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	oldStatic := builtinStatic
	builtinStatic = nil
	defer func() { builtinStatic = oldStatic }()

	cases := []struct {
		ip   string
		want Location
	}{
		{"10.1.2.3", Location{CountryCode: "lan", CountryName: "内网", Province: "内网"}},
		{"fd00::1", Location{CountryCode: "lan", CountryName: "内网", Province: "内网"}},
		{"203.0.113.7", Unknown},
		{"198.51.100.9", Unknown},
		{"", Unknown},
		{"abc", Unknown},
		{"999.1.1.1", Unknown},
	}

	for _, c := range cases {
		if got := LookupRequest(c.ip, nil); got != c.want {
			t.Fatalf("LookupRequest(%q) = %+v, want %+v", c.ip, got, c.want)
		}
	}
}

// TestLookupRequestHeaderPriority 验证请求头优先于其他来源。
func TestLookupRequestHeaderPriority(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	oldStatic := builtinStatic
	builtinStatic = nil
	defer func() { builtinStatic = oldStatic }()

	want := Location{CountryCode: "CN", CountryName: "中国", Province: "浙江"}
	getHeader := func(name string) string {
		if name == "X-Region" {
			return "CN:浙江"
		}
		return ""
	}

	if got := LookupRequest("203.0.113.7", getHeader); got != want {
		t.Fatalf("LookupRequest() = %+v, want %+v", got, want)
	}
}

// TestLookupRequestMMDBMissing 验证 MMDB 文件缺失时安全降级为未知。
func TestLookupRequestMMDBMissing(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "/nonexistent/x.mmdb")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	oldStatic := builtinStatic
	builtinStatic = nil
	defer func() { builtinStatic = oldStatic }()

	if got := LookupRequest("203.0.113.7", nil); got != Unknown {
		t.Fatalf("LookupRequest() = %+v, want %+v", got, Unknown)
	}
}

// TestLookupRequestBuiltinStatic 验证内置静态表生效且请求头可胜出。
func TestLookupRequestBuiltinStatic(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_MMDB", "")
	t.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	oldStatic := builtinStatic
	builtinStatic = NewStatic(map[string]Location{
		"1.2.3.4": {CountryCode: "TT", CountryName: "测试国", Province: "测试省"},
	})
	defer func() { builtinStatic = oldStatic }()

	want := Location{CountryCode: "TT", CountryName: "测试国", Province: "测试省"}
	if got := LookupRequest("1.2.3.4", nil); got != want {
		t.Fatalf("LookupRequest() = %+v, want %+v", got, want)
	}

	getHeader := func(string) string { return "US" }
	if got := LookupRequest("1.2.3.4", getHeader); got.CountryCode != "US" {
		t.Fatalf("LookupRequest().CountryCode = %q, want %q", got.CountryCode, "US")
	}
}

// TestLookupRequestConcurrent 验证并发查询下不出现 panic 与数据竞争。
func TestLookupRequestConcurrent(t *testing.T) {
	const goroutines = 100

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for i := 0; i < goroutines; i++ {
		go func() {
			defer wg.Done()
			_ = LookupRequest("203.0.113.7", nil)
		}()
	}
	wg.Wait()
}
