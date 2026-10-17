package geo

import (
	"os"
	"strings"
	"sync"
	"testing"
)

func TestHeaderNamesDefaultWhenEnvEmpty(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "")

	names := HeaderNames()

	want := []string{"X-Region", "X-Country-Code", "CF-IPCountry", "X-Client-Country"}
	if len(names) != len(want) {
		t.Fatalf("HeaderNames() 长度 = %d, 期望 %d", len(names), len(want))
	}
	for i, name := range names {
		if name != want[i] {
			t.Fatalf("HeaderNames()[%d] = %q, 期望 %q", i, name, want[i])
		}
	}
	if strings.Contains(strings.Join(names, ","), " ") {
		t.Fatalf("HeaderNames() 默认列表不应含空格: %v", names)
	}
}

func TestHeaderNamesTrimAndSkipEmpty(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "  X-One , , X-Two  ,,X-Three ")

	names := HeaderNames()

	want := []string{"X-One", "X-Two", "X-Three"}
	if len(names) != len(want) {
		t.Fatalf("HeaderNames() 长度 = %d, 期望 %d, 实际 %v", len(names), len(want), names)
	}
	for i, name := range names {
		if name != want[i] {
			t.Fatalf("HeaderNames()[%d] = %q, 期望 %q", i, name, want[i])
		}
		if strings.TrimSpace(name) != name {
			t.Fatalf("HeaderNames()[%d] = %q 未去除空白", i, name)
		}
	}
}

func TestHeaderNamesWhitespaceOnlyFallsBack(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "   \t  ")

	names := HeaderNames()

	if len(names) != 4 {
		t.Fatalf("空白环境变量应回退默认列表, 实际长度 %d: %v", len(names), names)
	}
	if names[0] != "X-Region" {
		t.Fatalf("回退后第一个头 = %q, 期望 X-Region", names[0])
	}
}

func TestLookupHeaderNilGetterReturnsUnknown(t *testing.T) {
	loc := LookupHeader(nil, []string{"X-Region"})

	if loc != Unknown {
		t.Fatalf("nil getter 应返回 Unknown, 实际 %+v", loc)
	}
	// 注：Unknown.CountryCode 为 "unknown" 而非空串，上面已断言 loc == Unknown
}

func TestLookupHeaderAllEmptyReturnsUnknown(t *testing.T) {
	get := func(name string) string { return "   " }

	loc := LookupHeader(get, []string{"X-Region", "X-Country-Code"})

	if loc != Unknown {
		t.Fatalf("全空请求头应返回 Unknown, 实际 %+v", loc)
	}
	if loc.CountryName != Unknown.CountryName {
		t.Fatalf("全空请求头 CountryName = %q, 期望 %q", loc.CountryName, Unknown.CountryName)
	}
}

func TestLookupHeaderPriorityFirstNonEmpty(t *testing.T) {
	values := map[string]string{
		"X-Region":       "JP:Tokyo",
		"X-Country-Code": "US:California",
	}
	get := func(name string) string { return values[name] }

	loc := LookupHeader(get, []string{"X-Region", "X-Country-Code"})

	if loc.CountryCode != "JP" {
		t.Fatalf("应优先取 X-Region, CountryCode = %q, 期望 JP", loc.CountryCode)
	}
	if loc.CountryName != "日本" {
		t.Fatalf("CountryName = %q, 期望 日本", loc.CountryName)
	}
	if loc.Province != "Tokyo" {
		t.Fatalf("Province = %q, 期望 Tokyo", loc.Province)
	}
}

func TestLookupHeaderCaseAndNoProvince(t *testing.T) {
	get := func(name string) string {
		if name == "CF-IPCountry" {
			return "cn"
		}
		return ""
	}

	loc := LookupHeader(get, []string{"X-Region", "CF-IPCountry"})

	if loc.CountryCode != "CN" {
		t.Fatalf("CountryCode = %q, 期望 CN", loc.CountryCode)
	}
	if loc.CountryName != "中国" {
		t.Fatalf("CountryName = %q, 期望 中国", loc.CountryName)
	}
	if loc.Province != Unknown.Province {
		t.Fatalf("无省份时应保持 Unknown.Province, 实际 %q", loc.Province)
	}
}

func TestLookupHeaderUnknownCountryKeepsCode(t *testing.T) {
	get := func(name string) string {
		if name == "X-Region" {
			return "zz:Somewhere"
		}
		return ""
	}

	loc := LookupHeader(get, []string{"X-Region"})

	if loc.CountryCode != "ZZ" {
		t.Fatalf("未知国家码应保留大写形式, 实际 %q", loc.CountryCode)
	}
	if loc.CountryName != "ZZ" {
		t.Fatalf("未知国家码的 CountryName 应等于码, 实际 %q", loc.CountryName)
	}
	if loc.Province != "Somewhere" {
		t.Fatalf("Province = %q, 期望 Somewhere", loc.Province)
	}
}

func TestLookupHeaderInvalidCountryLength(t *testing.T) {
	get := func(name string) string {
		if name == "X-Region" {
			return "CHN:Beijing"
		}
		return ""
	}

	loc := LookupHeader(get, []string{"X-Region"})

	if loc != Unknown {
		t.Fatalf("三位国家码应返回 Unknown, 实际 %+v", loc)
	}
	// 注：Unknown.CountryCode 为 "unknown" 而非空串，上面已断言 loc == Unknown
}

func TestLookupHeaderNonLetterCountry(t *testing.T) {
	get := func(name string) string {
		if name == "X-Region" {
			return "C1:Place"
		}
		return ""
	}

	loc := LookupHeader(get, []string{"X-Region"})

	if loc != Unknown {
		t.Fatalf("含非字母的国家码应返回 Unknown, 实际 %+v", loc)
	}
	if loc.Province != Unknown.Province {
		t.Fatalf("非法码不应解析省份, 实际 %q", loc.Province)
	}
}

func TestLookupHeaderSkipsBlankHeaderNames(t *testing.T) {
	values := map[string]string{"X-Two": "GB:England"}
	get := func(name string) string { return values[name] }

	loc := LookupHeader(get, []string{"   ", "", "X-Two"})

	if loc.CountryCode != "GB" {
		t.Fatalf("应跳过空白头名后命中 X-Two, CountryCode = %q", loc.CountryCode)
	}
	if loc.CountryName != "英国" {
		t.Fatalf("CountryName = %q, 期望 英国", loc.CountryName)
	}
}

func TestLookupHeaderConcurrentRaceFree(t *testing.T) {
	values := map[string]string{"X-Region": "SG:Singapore"}
	get := func(name string) string { return values[name] }

	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			loc := LookupHeader(get, []string{"X-Region"})
			if loc.CountryCode != "SG" {
				t.Errorf("并发调用 CountryCode = %q, 期望 SG", loc.CountryCode)
			}
			if loc.Province != "Singapore" {
				t.Errorf("并发调用 Province = %q, 期望 Singapore", loc.Province)
			}
		}()
	}
	wg.Wait()

	names := HeaderNames()
	if len(names) == 0 {
		t.Fatalf("并发后 HeaderNames() 不应为空")
	}
}

func TestHeaderNamesReadsEnvValue(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "Alpha,Beta")

	names := HeaderNames()

	if len(names) != 2 {
		t.Fatalf("长度 = %d, 期望 2: %v", len(names), names)
	}
	if names[0] != "Alpha" || names[1] != "Beta" {
		t.Fatalf("解析结果 = %v, 期望 [Alpha Beta]", names)
	}
	if _, ok := os.LookupEnv("LINKSHORT_GEO_HEADERS"); !ok {
		t.Fatalf("环境变量应被设置")
	}
}
