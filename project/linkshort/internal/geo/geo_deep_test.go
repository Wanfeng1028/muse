package geo

import (
	"net"
	"strings"
	"sync"
	"testing"
)

func TestNormalizeIPRejectsReservedRanges(t *testing.T) {
	cases := []struct {
		name string
		ip   string
		ok   bool
	}{
		{"空字符串", "", false},
		{"纯空格", "   ", false},
		{"非法文本", "not-an-ip", false},
		{"私网10段", "10.1.2.3", false},
		{"私网172段", "172.16.0.9", false},
		{"私网192段", "192.168.1.1", false},
		{"回环", "127.0.0.1", false},
		{"IPv6回环", "::1", false},
		{"组播", "224.0.0.1", false},
		{"未指定", "0.0.0.0", false},
		{"链路本地", "169.254.10.10", false},
		{"公网IPv4", "8.8.8.8", true},
		{"公网IPv4带空格", "  1.1.1.1  ", true},
		{"公网IPv6", "2001:4860:4860::8888", true},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			ip, ok := normalizeIP(c.ip)
			if ok != c.ok {
				t.Fatalf("normalizeIP(%q) ok=%v, 期望 %v", c.ip, ok, c.ok)
			}
			if ok {
				if ip == nil {
					t.Fatalf("normalizeIP(%q) 返回 ok 但 ip 为 nil", c.ip)
				}
				if ip.IsPrivate() || ip.IsLoopback() || ip.IsMulticast() || ip.IsUnspecified() || ip.IsLinkLocalUnicast() {
					t.Fatalf("normalizeIP(%q) 放行了保留地址 %v", c.ip, ip)
				}
			}
			if !ok && ip != nil {
				t.Fatalf("normalizeIP(%q) 返回 false 但 ip 非 nil: %v", c.ip, ip)
			}
		})
	}
}

func TestNormalizeIPTrimDoesNotBypassValidation(t *testing.T) {
	_, ok := normalizeIP("\t10.0.0.1\n")
	if ok {
		t.Fatalf("带空白包裹的私网地址 10.0.0.1 被放行")
	}

	_, ok = normalizeIP(" \t 8.8.4.4 \n ")
	if !ok {
		t.Fatalf("带空白包裹的公网地址 8.8.4.4 被拒绝")
	}
}

func TestPickNamePrecedenceChain(t *testing.T) {
	cases := []struct {
		name     string
		names    map[string]string
		fallback string
		want     string
	}{
		{
			name:     "优先zh-CN",
			names:    map[string]string{"zh-CN": "中国", "en": "China"},
			fallback: "CN",
			want:     "中国",
		},
		{
			name:     "zh-CN为空退到en",
			names:    map[string]string{"zh-CN": "", "en": "China"},
			fallback: "CN",
			want:     "China",
		},
		{
			name:     "zh-CN和en都空用fallback",
			names:    map[string]string{"zh-CN": "", "en": ""},
			fallback: "CN",
			want:     "CN",
		},
		{
			name:     "names为nil用fallback",
			names:    nil,
			fallback: "US",
			want:     "US",
		},
		{
			name:     "全空落回Unknown.CountryName",
			names:    nil,
			fallback: "",
			want:     Unknown.CountryName,
		},
		{
			name:     "names无zh-CN无en用fallback",
			names:    map[string]string{"ja": "日本"},
			fallback: "JP",
			want:     "JP",
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := pickName(c.names, c.fallback)
			if got != c.want {
				t.Fatalf("pickName(names=%v, fallback=%q) = %q, 期望 %q", c.names, c.fallback, got, c.want)
			}
			if got == "" {
				t.Fatalf("pickName 返回了空字符串，不符合契约")
			}
		})
	}
}

func TestStaticResolverLookupHitAndMiss(t *testing.T) {
	table := map[string]Location{
		"8.8.8.8": {
			CountryCode: "US",
			CountryName: "美国",
			Province:    "加州",
			City:        "山景城",
		},
		"1.1.1.1": {
			CountryCode: "AU",
			CountryName: "澳大利亚",
			Province:    "昆士兰",
			City:        "布里斯班",
		},
	}
	r := NewStatic(table)
	if r == nil {
		t.Fatalf("NewStatic 返回了 nil")
	}

	got := r.Lookup("8.8.8.8")
	if got.CountryCode != "US" {
		t.Fatalf("命中 8.8.8.8 得到 CountryCode=%q, 期望 US", got.CountryCode)
	}
	if got.City != "山景城" {
		t.Fatalf("命中 8.8.8.8 得到 City=%q, 期望 山景城", got.City)
	}

	miss := r.Lookup("9.9.9.9")
	if miss != Unknown {
		t.Fatalf("未命中的 9.9.9.9 得到 %+v, 期望 Unknown", miss)
	}
	if miss.CountryCode != "unknown" || miss.City != "unknown" {
		t.Fatalf("未命中结果字段不是 unknown: %+v", miss)
	}
}

func TestStaticResolverRejectsInvalidAndReservedIP(t *testing.T) {
	table := map[string]Location{
		"10.0.0.1":  {CountryCode: "CN", CountryName: "中国", Province: "广东", City: "广州"},
		"127.0.0.1": {CountryCode: "CN", CountryName: "中国", Province: "广东", City: "广州"},
		"abc":       {CountryCode: "CN", CountryName: "中国", Province: "广东", City: "广州"},
	}
	r := NewStatic(table)

	for _, ip := range []string{"10.0.0.1", "127.0.0.1", "abc", ""} {
		got := r.Lookup(ip)
		if got != Unknown {
			t.Fatalf("Lookup(%q) 得到 %+v, 期望 Unknown（保留/非法地址必须被拦）", ip, got)
		}
	}
}

func TestStaticResolverNilSafety(t *testing.T) {
	var nilResolver *staticResolver
	if got := nilResolver.Lookup("8.8.8.8"); got != Unknown {
		t.Fatalf("nil staticResolver.Lookup 得到 %+v, 期望 Unknown", got)
	}

	empty := NewStatic(nil)
	if got := empty.Lookup("8.8.8.8"); got != Unknown {
		t.Fatalf("NewStatic(nil).Lookup 得到 %+v, 期望 Unknown", got)
	}

	if got := NewStatic(map[string]Location{}).Lookup("1.1.1.1"); got != Unknown {
		t.Fatalf("空表 Lookup 得到 %+v, 期望 Unknown", got)
	}
}

func TestStaticResolverConcurrentLookupRaceFree(t *testing.T) {
	table := map[string]Location{
		"8.8.8.8": {CountryCode: "US", CountryName: "美国", Province: "加州", City: "山景城"},
		"1.1.1.1": {CountryCode: "AU", CountryName: "澳大利亚", Province: "昆士兰", City: "布里斯班"},
	}
	r := NewStatic(table)

	const workers = 32
	const loops = 200
	var wg sync.WaitGroup
	wg.Add(workers)
	errCh := make(chan string, workers)

	for i := 0; i < workers; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < loops; j++ {
				if id%2 == 0 {
					got := r.Lookup("8.8.8.8")
					if got.CountryCode != "US" || got.City != "山景城" {
						errCh <- "并发命中 8.8.8.8 结果不一致"
						return
					}
				} else {
					got := r.Lookup("1.1.1.1")
					if got.CountryCode != "AU" || got.Province != "昆士兰" {
						errCh <- "并发命中 1.1.1.1 结果不一致"
						return
					}
				}
			}
		}(i)
	}

	wg.Wait()
	close(errCh)
	for msg := range errCh {
		t.Fatalf("并发读出错: %s", msg)
	}

	final := r.Lookup("8.8.8.8")
	if final.CountryName != "美国" {
		t.Fatalf("并发读后 8.8.8.8 数据被破坏: %+v", final)
	}
}

func TestOpenEmptyPathReturnsErrEmptyPath(t *testing.T) {
	db, err := Open("")
	if err == nil {
		t.Fatalf("Open(\"\") 返回 err=nil, 期望 errEmptyPath")
	}
	if err != errEmptyPath {
		t.Fatalf("Open(\"\") 返回 err=%v, 期望 errEmptyPath", err)
	}
	if db != nil {
		t.Fatalf("Open(\"\") 返回非 nil DB: %+v", db)
	}
}

func TestOpenMissingFileReturnsError(t *testing.T) {
	db, err := Open("/no/such/path/definitely-not-exist.mmdb")
	if err == nil {
		t.Fatalf("Open 不存在的文件返回 err=nil, 期望错误")
	}
	if db != nil {
		t.Fatalf("Open 失败却返回非 nil DB: %+v", db)
	}
	if err == errEmptyPath {
		t.Fatalf("Open 缺失文件不应返回 errEmptyPath")
	}
}

func TestDBNilSafetyAndCloseNil(t *testing.T) {
	var nilDB *DB
	if got := nilDB.Lookup("8.8.8.8"); got != Unknown {
		t.Fatalf("nil *DB Lookup 得到 %+v, 期望 Unknown", got)
	}
	if err := nilDB.Close(); err != nil {
		t.Fatalf("nil *DB Close 得到 err=%v, 期望 nil", err)
	}

	emptyReader := &DB{}
	if got := emptyReader.Lookup("8.8.8.8"); got != Unknown {
		t.Fatalf("reader 为 nil 的 DB Lookup 得到 %+v, 期望 Unknown", got)
	}
	if err := emptyReader.Close(); err != nil {
		t.Fatalf("reader 为 nil 的 DB Close 得到 err=%v, 期望 nil", err)
	}
}

func TestFromEnvReturnsWorkingResolver(t *testing.T) {
	r := FromEnv()
	if r == nil {
		t.Fatalf("FromEnv 返回 nil")
	}

	got := r.Lookup("10.0.0.1")
	wantLan := Location{CountryCode: "lan", CountryName: "内网", Province: "内网", City: "内网"}
	if got != wantLan {
		t.Fatalf("FromEnv().Lookup(10.0.0.1) 得到 %+v, 期望内网 Location %+v", got, wantLan)
	}

	got = r.Lookup("not-an-ip")
	if got != Unknown {
		t.Fatalf("FromEnv().Lookup(not-an-ip) 得到 %+v, 期望 Unknown", got)
	}

	got = r.Lookup("")
	if got != Unknown {
		t.Fatalf("FromEnv().Lookup(\"\") 得到 %+v, 期望 Unknown", got)
	}

	got = r.Lookup("  8.8.8.8  ")
	if got.CountryCode == "" {
		t.Fatalf("FromEnv().Lookup(8.8.8.8) CountryCode 为空，违反 Location 契约")
	}
}

func TestUnknownIsZeroSentinel(t *testing.T) {
	if Unknown.CountryCode != "unknown" {
		t.Fatalf("Unknown.CountryCode=%q, 期望 unknown", Unknown.CountryCode)
	}
	if Unknown.CountryName != "unknown" {
		t.Fatalf("Unknown.CountryName=%q, 期望 unknown", Unknown.CountryName)
	}
	if Unknown.Province != "unknown" {
		t.Fatalf("Unknown.Province=%q, 期望 unknown", Unknown.Province)
	}
	if Unknown.City != "unknown" {
		t.Fatalf("Unknown.City=%q, 期望 unknown", Unknown.City)
	}

	fields := []string{Unknown.CountryCode, Unknown.CountryName, Unknown.Province, Unknown.City}
	for _, f := range fields {
		if strings.TrimSpace(f) != f {
			t.Fatalf("Unknown 字段 %q 含首尾空白", f)
		}
	}

	parsed := net.ParseIP("8.8.8.8")
	if parsed == nil {
		t.Fatalf("net.ParseIP 基准值解析失败，测试环境异常")
	}
}
