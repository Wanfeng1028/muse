package geo

import (
	"net"
	"os"
	"strings"
	"sync"
	"testing"
)

type fixedResolver struct {
	loc Location
}

func (f fixedResolver) Lookup(ip string) Location {
	return f.loc
}

type countResolver struct {
	mu    sync.Mutex
	calls int
	loc   Location
}

func (c *countResolver) Lookup(ip string) Location {
	c.mu.Lock()
	c.calls++
	c.mu.Unlock()
	return c.loc
}

func (c *countResolver) Calls() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.calls
}

func withChainState(t *testing.T, mmdb Resolver, names []string) {
	t.Helper()
	chainMu.Lock()
	prevMMDB := chainMMDB
	prevNames := chainHeaderNames
	chainMMDB = mmdb
	chainHeaderNames = names
	chainMu.Unlock()
	t.Cleanup(func() {
		chainMu.Lock()
		chainMMDB = prevMMDB
		chainHeaderNames = prevNames
		chainMu.Unlock()
	})
}

func TestLookupRequestInvalidIPReturnsUnknown(t *testing.T) {
	withChainState(t, nil, []string{"X-Real-IP"})

	cases := []string{"", "   ", "not-an-ip", "999.999.999.999", "12.34.56"}
	for _, raw := range cases {
		got := LookupRequest(raw, func(string) string { return "1.2.3.4" })
		if got != Unknown {
			t.Fatalf("非法 IP %q 期望 Unknown，实际 %+v", raw, got)
		}
		// 注：Unknown 的各字段为 "unknown" 而非空串，上面已断言 got == Unknown
	}
}

func TestLookupRequestPrivateAndLoopbackReturnLan(t *testing.T) {
	withChainState(t, fixedResolver{loc: Location{CountryCode: "us", CountryName: "美国", Province: "CA", City: "LA"}}, []string{"X-Real-IP"})

	cases := []string{
		"10.0.0.1",
		"192.168.1.1",
		"172.16.5.5",
		"127.0.0.1",
		"::1",
		"fe80::1",
		"224.0.0.1",
		"0.0.0.0",
	}
	for _, raw := range cases {
		got := LookupRequest(raw, func(string) string { return "8.8.8.8" })
		if got.CountryCode != "lan" {
			t.Fatalf("内网/回环 IP %q 期望 CountryCode=lan，实际 %q", raw, got.CountryCode)
		}
		if got.CountryName != "内网" || got.Province != "内网" || got.City != "内网" {
			t.Fatalf("内网/回环 IP %q 期望内网全字段，实际 %+v", raw, got)
		}
	}
}

func TestLookupRequestHeaderWinsOverMMDB(t *testing.T) {
	headerLoc := Location{CountryCode: "jp", CountryName: "日本", Province: "东京", City: "东京"}
	mmdbLoc := Location{CountryCode: "us", CountryName: "美国", Province: "CA", City: "LA"}
	cr := &countResolver{loc: mmdbLoc}
	withChainState(t, cr, []string{"X-Real-IP", "X-Forwarded-For"})

	getHeader := func(name string) string {
		if name == "X-Forwarded-For" {
			return "jp"
		}
		return ""
	}
	got := LookupRequest("8.8.8.8", getHeader)
	if got.CountryCode != "JP" { // 产品对国家码做 ToUpper
		t.Fatalf("期望命中云厂商头 jp，实际 %+v", got)
	}
	if cr.Calls() != 0 {
		t.Fatalf("头命中后不应再查 MMDB，实际调用 %d 次", cr.Calls())
	}
	_ = headerLoc
}

func TestLookupRequestMMDBUsedWhenHeaderMisses(t *testing.T) {
	mmdbLoc := Location{CountryCode: "de", CountryName: "德国", Province: "BE", City: "柏林"}
	cr := &countResolver{loc: mmdbLoc}
	withChainState(t, cr, []string{"X-Real-IP"})

	got := LookupRequest("8.8.8.8", func(string) string { return "" })
	if got.CountryCode != "de" {
		t.Fatalf("头未命中时期望 MMDB de，实际 %+v", got)
	}
	if cr.Calls() != 1 {
		t.Fatalf("期望 MMDB 查询 1 次，实际 %d 次", cr.Calls())
	}
}

func TestLookupRequestNilHeaderSkipsHeaderStage(t *testing.T) {
	mmdbLoc := Location{CountryCode: "fr", CountryName: "法国", Province: "IDF", City: "巴黎"}
	cr := &countResolver{loc: mmdbLoc}
	withChainState(t, cr, []string{"X-Real-IP"})

	got := LookupRequest("8.8.8.8", nil)
	if got.CountryCode != "fr" {
		t.Fatalf("getHeader 为 nil 时应落到 MMDB，期望 fr，实际 %+v", got)
	}
	if cr.Calls() != 1 {
		t.Fatalf("期望 MMDB 查询 1 次，实际 %d 次", cr.Calls())
	}
}

func TestLookupRequestMMDBUnknownFallsToBuiltin(t *testing.T) {
	withChainState(t, fixedResolver{loc: Unknown}, []string{"X-Real-IP"})

	prevBuiltin := builtinStatic
	builtinStatic = fixedResolver{loc: Location{CountryCode: "cn", CountryName: "中国", Province: "广东", City: "深圳"}}
	t.Cleanup(func() { builtinStatic = prevBuiltin })

	got := LookupRequest("8.8.8.8", func(string) string { return "" })
	if got.CountryCode != "cn" {
		t.Fatalf("MMDB 未命中时应落到内置表 cn，实际 %+v", got)
	}
	if got.City != "深圳" {
		t.Fatalf("内置表命中时期望 City=深圳，实际 %q", got.City)
	}
}

func TestLookupRequestAllStagesMissReturnsUnknown(t *testing.T) {
	withChainState(t, fixedResolver{loc: Unknown}, []string{"X-Real-IP"})

	prevBuiltin := builtinStatic
	builtinStatic = fixedResolver{loc: Unknown}
	t.Cleanup(func() { builtinStatic = prevBuiltin })

	got := LookupRequest("8.8.8.8", func(string) string { return "" })
	if got != Unknown {
		t.Fatalf("所有阶段未命中期望 Unknown，实际 %+v", got)
	}
	// 注：Unknown 的各字段为 "unknown" 而非空串，上面已断言 got == Unknown
}

func TestLookupRequestTrimsWhitespaceIP(t *testing.T) {
	withChainState(t, fixedResolver{loc: Location{CountryCode: "us", CountryName: "美国", Province: "CA", City: "LA"}}, []string{"X-Real-IP"})

	got := LookupRequest("  8.8.8.8  ", func(string) string { return "" })
	if got.CountryCode != "us" {
		t.Fatalf("带空白 IP 应被 TrimSpace 后解析，期望 us，实际 %+v", got)
	}
	if got.City != "LA" {
		t.Fatalf("期望 City=LA，实际 %q", got.City)
	}
}

func TestReloadFromEnvEmptyPathSetsNilMMDB(t *testing.T) {
	prevMMDBPath := os.Getenv("LINKSHORT_GEO_MMDB")
	prevGeoPath := os.Getenv("GEOIP_MMDB_PATH")
	t.Cleanup(func() {
		os.Setenv("LINKSHORT_GEO_MMDB", prevMMDBPath)
		os.Setenv("GEOIP_MMDB_PATH", prevGeoPath)
		ReloadFromEnv()
	})

	os.Setenv("LINKSHORT_GEO_MMDB", "")
	os.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	if currentMMDB() != nil {
		t.Fatalf("未配置路径时期望 chainMMDB 为 nil，实际 %v", currentMMDB())
	}
	if got := currentHeaderNames(); got == nil {
		t.Fatalf("chainHeaderNames 期望非 nil，实际 nil")
	}
}

func TestReloadFromEnvMissingFileFallsBackNil(t *testing.T) {
	prevMMDBPath := os.Getenv("LINKSHORT_GEO_MMDB")
	prevGeoPath := os.Getenv("GEOIP_MMDB_PATH")
	t.Cleanup(func() {
		os.Setenv("LINKSHORT_GEO_MMDB", prevMMDBPath)
		os.Setenv("GEOIP_MMDB_PATH", prevGeoPath)
		ReloadFromEnv()
	})

	os.Setenv("LINKSHORT_GEO_MMDB", "/nonexistent/path/does-not-exist.mmdb")
	os.Setenv("GEOIP_MMDB_PATH", "")
	ReloadFromEnv()

	if currentMMDB() != nil {
		t.Fatalf("打开失败时期望降级为 nil，实际 %v", currentMMDB())
	}
	if currentHeaderNames() == nil {
		t.Fatalf("打开失败后 chainHeaderNames 期望非 nil，实际 nil")
	}
}

func TestReloadFromEnvConcurrentWithLookup(t *testing.T) {
	prevMMDBPath := os.Getenv("LINKSHORT_GEO_MMDB")
	prevGeoPath := os.Getenv("GEOIP_MMDB_PATH")
	t.Cleanup(func() {
		os.Setenv("LINKSHORT_GEO_MMDB", prevMMDBPath)
		os.Setenv("GEOIP_MMDB_PATH", prevGeoPath)
		ReloadFromEnv()
	})

	os.Setenv("LINKSHORT_GEO_MMDB", "")
	os.Setenv("GEOIP_MMDB_PATH", "")

	var wg sync.WaitGroup
	stop := make(chan struct{})

	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			select {
			case <-stop:
				return
			default:
				ReloadFromEnv()
			}
		}
	}()

	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 200; j++ {
				got := LookupRequest("8.8.8.8", func(name string) string {
					if strings.EqualFold(name, "X-Real-IP") {
						return ""
					}
					return ""
				})
				if got.CountryCode == "lan" {
					t.Errorf("公网 IP 8.8.8.8 不应解析为内网，实际 %+v", got)
				}
			}
		}()
	}

	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 200; j++ {
				if net.ParseIP("127.0.0.1") == nil {
					t.Errorf("net.ParseIP 对回环地址返回 nil")
				}
				_ = currentHeaderNames()
				_ = currentMMDB()
			}
		}()
	}

	close(stop)
	wg.Wait()
}

func TestRequestResolverAdapterDelegatesToLookupRequest(t *testing.T) {
	withChainState(t, fixedResolver{loc: Location{CountryCode: "sg", CountryName: "新加坡", Province: "SG", City: "新加坡"}}, []string{"X-Real-IP"})

	var r requestResolver
	got := r.Lookup("8.8.8.8")
	if got.CountryCode != "sg" {
		t.Fatalf("requestResolver.Lookup 期望 sg，实际 %+v", got)
	}
	if got.City != "新加坡" {
		t.Fatalf("requestResolver.Lookup 期望 City=新加坡，实际 %q", got.City)
	}

	lan := r.Lookup("10.1.2.3")
	if lan.CountryCode != "lan" {
		t.Fatalf("requestResolver.Lookup 内网期望 lan，实际 %+v", lan)
	}
	if lan.CountryName != "内网" {
		t.Fatalf("requestResolver.Lookup 内网期望 CountryName=内网，实际 %q", lan.CountryName)
	}
}
