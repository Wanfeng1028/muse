package geo

import (
	"net"
	"sync"
	"testing"
)

func TestChinaLookupExactPrefixWins(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "10.0.0.0/8"), ones: 8, cc: "CN", country: "中国", province: "北京"},
		{network: mustCIDR(t, "10.1.0.0/16"), ones: 16, cc: "CN", country: "中国", province: "广东"},
	}}

	got := r.Lookup("10.1.2.3")

	if got.Province != "广东" {
		t.Fatalf("期望命中最长前缀 16 位段的省份为广东，实际得到 %q", got.Province)
	}
	if got.CountryCode != "CN" {
		t.Fatalf("期望国家代码为 CN，实际得到 %q", got.CountryCode)
	}
}

func TestChinaLookupShorterPrefixUsedWhenLongerMisses(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "10.0.0.0/8"), ones: 8, cc: "CN", country: "中国", province: "北京"},
		{network: mustCIDR(t, "10.1.0.0/16"), ones: 16, cc: "CN", country: "中国", province: "广东"},
	}}

	got := r.Lookup("10.9.9.9")

	if got.Province != "北京" {
		t.Fatalf("期望回落到 8 位段的省份为北京，实际得到 %q", got.Province)
	}
	if got.CountryName != "中国" {
		t.Fatalf("期望国家名称为中国，实际得到 %q", got.CountryName)
	}
}

func TestChinaLookupUnknownWhenNoRangeMatches(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "10.0.0.0/8"), ones: 8, cc: "CN", country: "中国", province: "北京"},
	}}

	got := r.Lookup("203.0.113.7")

	if got != Unknown {
		t.Fatalf("期望未收录地址返回 Unknown，实际得到 %+v", got)
	}
	if got.Province != Unknown.Province {
		t.Fatalf("期望省份为 %q，实际得到 %q", Unknown.Province, got.Province)
	}
}

func TestChinaLookupInvalidInputReturnsUnknown(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "10.0.0.0/8"), ones: 8, cc: "CN", country: "中国", province: "北京"},
	}}

	for _, input := range []string{"", "   ", "not-an-ip", "999.999.999.999", "10.0.0.0/8"} {
		got := r.Lookup(input)
		if got != Unknown {
			t.Fatalf("输入 %q 期望返回 Unknown，实际得到 %+v", input, got)
		}
	}
}

func TestChinaLookupNilResolverReturnsUnknown(t *testing.T) {
	var r *cidrResolver

	got := r.Lookup("114.114.114.114")

	if got != Unknown {
		t.Fatalf("nil 解析器期望返回 Unknown，实际得到 %+v", got)
	}
	if got.CountryCode != Unknown.CountryCode {
		t.Fatalf("期望国家代码为 %q，实际得到 %q", Unknown.CountryCode, got.CountryCode)
	}
}

func TestChinaLookupTrimsWhitespace(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "114.114.114.0/24"), ones: 24, cc: "CN", country: "中国", province: "江苏"},
	}}

	got := r.Lookup("  114.114.114.114  ")

	if got.Province != "江苏" {
		t.Fatalf("期望去除空白后命中江苏，实际得到 %q", got.Province)
	}
	if got.CountryCode != "CN" {
		t.Fatalf("期望国家代码为 CN，实际得到 %q", got.CountryCode)
	}
}

func TestChinaLookupCityAlwaysUnknown(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "223.5.5.0/24"), ones: 24, cc: "CN", country: "中国", province: "浙江"},
	}}

	got := r.Lookup("223.5.5.5")

	if got.City != Unknown.City {
		t.Fatalf("期望城市恒为 %q，实际得到 %q", Unknown.City, got.City)
	}
	if got.Province != "浙江" {
		t.Fatalf("期望省份为浙江，实际得到 %q", got.Province)
	}
}

func TestChinaLookupIPv6PrefixMatch(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "2400:3200::/32"), ones: 32, cc: "CN", country: "中国", province: "浙江"},
	}}

	got := r.Lookup("2400:3200::1")

	if got.Province != "浙江" {
		t.Fatalf("期望 IPv6 命中浙江，实际得到 %q", got.Province)
	}
	if got.CountryCode != "CN" {
		t.Fatalf("期望国家代码为 CN，实际得到 %q", got.CountryCode)
	}
}

func TestChinaLookupBoundaryAddresses(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: mustCIDR(t, "114.114.114.0/24"), ones: 24, cc: "CN", country: "中国", province: "江苏"},
	}}

	first := r.Lookup("114.114.114.0")
	last := r.Lookup("114.114.114.255")
	outside := r.Lookup("114.114.115.1")

	if first.Province != "江苏" {
		t.Fatalf("期望网段首地址命中江苏，实际得到 %q", first.Province)
	}
	if last.Province != "江苏" {
		t.Fatalf("期望网段末地址命中江苏，实际得到 %q", last.Province)
	}
	if outside != Unknown {
		t.Fatalf("期望网段外地址返回 Unknown，实际得到 %+v", outside)
	}
}

func TestChinaLookupBuiltinStaticConcurrentSafe(t *testing.T) {
	if builtinStatic == nil {
		t.Fatal("期望 builtinStatic 在 init 后非空")
	}

	var wg sync.WaitGroup
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			got := builtinStatic.Lookup("114.114.114.114")
			if got.Province != "江苏" {
				t.Errorf("并发查询期望命中江苏，实际得到 %q", got.Province)
			}
		}()
	}
	wg.Wait()

	verify := builtinStatic.Lookup("223.5.5.5")
	if verify.Province != "浙江" {
		t.Fatalf("并发后期望内置表仍命中浙江，实际得到 %q", verify.Province)
	}
}

func TestChinaLookupSkipsNilNetworkEntries(t *testing.T) {
	r := &cidrResolver{nets: []chinaRange{
		{network: nil, ones: 64, cc: "CN", country: "中国", province: "北京"},
		{network: mustCIDR(t, "119.29.29.0/24"), ones: 24, cc: "CN", country: "中国", province: "广东"},
	}}

	got := r.Lookup("119.29.29.29")

	if got.Province != "广东" {
		t.Fatalf("期望跳过 nil 网段后命中广东，实际得到 %q", got.Province)
	}
	if got.CountryName != "中国" {
		t.Fatalf("期望国家名称为中国，实际得到 %q", got.CountryName)
	}
}

func mustCIDR(t *testing.T, cidr string) *net.IPNet {
	t.Helper()
	_, network, err := net.ParseCIDR(cidr)
	if err != nil {
		t.Fatalf("测试用 CIDR %q 解析失败: %v", cidr, err)
	}
	return network
}
