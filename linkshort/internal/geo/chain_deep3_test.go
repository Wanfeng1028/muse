package geo

import (
	"os"
	"testing"
)

// TestLookupRequestIPv6SpecialAddrsLan 覆盖 IPv6 特殊地址的 lan 短路分支：
// ::1（回环）、fe80::1（链路本地）、ff02::1（组播）、::（未指定）均应在 header/mmdb/builtin 之前返回 lan。
func TestLookupRequestIPv6SpecialAddrsLan(t *testing.T) {
	withChainState(t, nil, nil)

	cases := []string{"::1", "fe80::1", "ff02::1", "::"}
	for _, ip := range cases {
		ip := ip
		t.Run(ip, func(t *testing.T) {
			loc := LookupRequest(ip, nil)
			if loc.CountryCode != "lan" {
				t.Fatalf("LookupRequest(%q).CountryCode = %q, want %q", ip, loc.CountryCode, "lan")
			}
			if loc.CountryName != "内网" || loc.Province != "内网" || loc.City != "内网" {
				t.Fatalf("LookupRequest(%q) = %+v, want lan 内网 内网 内网", ip, loc)
			}
		})
	}
}

// TestLookupRequestLanShortCircuitsChain 覆盖 lan 分支在 header 与 mmdb 之前短路：
// 内网 IP 时，getHeader 计数器与 mmdb Calls() 都必须保持 0。
func TestLookupRequestLanShortCircuitsChain(t *testing.T) {
	mmdb := &countResolver{loc: Location{CountryCode: "DE", CountryName: "德国", Province: "BE", City: "柏林"}}
	withChainState(t, mmdb, []string{"X-Country"})

	headerCalls := 0
	getHeader := func(name string) string {
		headerCalls++
		return "US"
	}

	loc := LookupRequest("10.9.9.9", getHeader)
	if loc.CountryCode != "lan" {
		t.Fatalf("LookupRequest(10.9.9.9).CountryCode = %q, want %q", loc.CountryCode, "lan")
	}
	if headerCalls != 0 {
		t.Fatalf("getHeader called %d times, want 0 (lan 应短路 header)", headerCalls)
	}
	if got := mmdb.Calls(); got != 0 {
		t.Fatalf("mmdb Lookup called %d times, want 0 (lan 应短路 mmdb)", got)
	}
}

// TestLookupRequestBroadcastUnknown 覆盖广播地址不属于 lan 判定：
// 255.255.255.255 不满足 IsPrivate/IsLoopback/IsLinkLocalUnicast/IsMulticast/IsUnspecified，
// 且不在内置表中，最终返回 Unknown。
func TestLookupRequestBroadcastUnknown(t *testing.T) {
	withChainState(t, nil, nil)

	loc := LookupRequest("255.255.255.255", nil)
	if loc != Unknown {
		t.Fatalf("LookupRequest(255.255.255.255) = %+v, want Unknown", loc)
	}
}

// TestLookupRequestMalformedHeaderFallsThrough 覆盖 LookupHeader 返回 Unknown 时不视为命中：
// 3 字母国家码非法 → 责任链继续走 mmdb，最终返回 mmdb 结果。
func TestLookupRequestMalformedHeaderFallsThrough(t *testing.T) {
	mmdb := &countResolver{loc: Location{CountryCode: "DE", CountryName: "德国", Province: "BE", City: "柏林"}}
	withChainState(t, mmdb, []string{"X-Country"})

	getHeader := func(name string) string {
		if name == "X-Country" {
			return "USA"
		}
		return ""
	}

	loc := LookupRequest("8.8.8.8", getHeader)
	if loc.CountryCode != "DE" {
		t.Fatalf("LookupRequest with malformed header = %+v, want CountryCode DE", loc)
	}
	if got := mmdb.Calls(); got != 1 {
		t.Fatalf("mmdb Lookup called %d times, want 1 (头非法不算命中，继续走责任链)", got)
	}
}

// TestLookupRequestEnvHeaderNamesEndToEnd 覆盖 LINKSHORT_GEO_HEADERS 环境变量配置真正进入责任链：
// 8.8.8.8 在内置表是 US，但 env 配置的 X-Custom-Region 返回 JP，头命中优先，结果应为 JP。
func TestLookupRequestEnvHeaderNamesEndToEnd(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "X-Custom-Region")
	ReloadFromEnv()
	t.Cleanup(func() {
		os.Unsetenv("LINKSHORT_GEO_HEADERS")
		ReloadFromEnv()
	})

	getHeader := func(name string) string {
		if name == "X-Custom-Region" {
			return "JP"
		}
		return ""
	}

	loc := LookupRequest("8.8.8.8", getHeader)
	if loc.CountryCode != "JP" {
		t.Fatalf("LookupRequest(8.8.8.8).CountryCode = %q, want %q", loc.CountryCode, "JP")
	}
	if loc.CountryName != "日本" {
		t.Fatalf("LookupRequest(8.8.8.8).CountryName = %q, want %q", loc.CountryName, "日本")
	}
}

// TestLookupRequestBuiltinNilGuard 覆盖 builtinStatic 为 nil 时的防御分支：
// builtinStatic 暂置 nil 后，china 表失效，责任链走到底返回 Unknown。
func TestLookupRequestBuiltinNilGuard(t *testing.T) {
	orig := builtinStatic
	builtinStatic = nil
	t.Cleanup(func() {
		builtinStatic = orig
	})

	withChainState(t, nil, nil)

	loc := LookupRequest("114.114.114.114", nil)
	if loc != Unknown {
		t.Fatalf("LookupRequest(114.114.114.114) with nil builtinStatic = %+v, want Unknown", loc)
	}
}

// TestLookupRequestMMDBUnknownFallsToBuiltin_Deep3 覆盖 mmdb 返回 Unknown 时责任链继续落到内置表：
// mmdb 返回 Unknown 不算命中，最终由 china 表给出 CN/江苏。
func TestLookupRequestMMDBUnknownFallsToBuiltin_Deep3(t *testing.T) {
	withChainState(t, fixedResolver{loc: Unknown}, nil)

	loc := LookupRequest("114.114.114.114", nil)
	if loc.CountryCode != "CN" {
		t.Fatalf("LookupRequest(114.114.114.114).CountryCode = %q, want %q", loc.CountryCode, "CN")
	}
	if loc.Province != "江苏" {
		t.Fatalf("LookupRequest(114.114.114.114).Province = %q, want %q", loc.Province, "江苏")
	}
}

// TestLookupRequestIPv6ChinaTable 覆盖 IPv6 地址落到内置表的分支：
// 2400:3200::1 在 china 表为 CN/浙江。
func TestLookupRequestIPv6ChinaTable(t *testing.T) {
	withChainState(t, nil, nil)

	loc := LookupRequest("2400:3200::1", nil)
	if loc.CountryCode != "CN" {
		t.Fatalf("LookupRequest(2400:3200::1).CountryCode = %q, want %q", loc.CountryCode, "CN")
	}
	if loc.Province != "浙江" {
		t.Fatalf("LookupRequest(2400:3200::1).Province = %q, want %q", loc.Province, "浙江")
	}
}

// ipRecordingResolver 记录收到的 ip 参数并返回 Unknown，用于验证 LookupRequest 传入 mmdb 的是 TrimSpace 后的值。
type ipRecordingResolver struct {
	gotIP string
}

func (r *ipRecordingResolver) Lookup(ip string) Location {
	r.gotIP = ip
	return Unknown
}

// TestLookupRequestTrimsIPForMMDB 覆盖传给 mmdb 的 ip 已经 TrimSpace：
// 输入 "  8.8.8.8  "，resolver 收到的应为 "8.8.8.8"，且 mmdb 返回 Unknown 后落到内置表为 US。
func TestLookupRequestTrimsIPForMMDB(t *testing.T) {
	rec := &ipRecordingResolver{}
	withChainState(t, rec, nil)

	loc := LookupRequest("  8.8.8.8  ", nil)
	if rec.gotIP != "8.8.8.8" {
		t.Fatalf("mmdb received ip %q, want %q", rec.gotIP, "8.8.8.8")
	}
	if loc.CountryCode != "US" {
		t.Fatalf("LookupRequest(\"  8.8.8.8  \").CountryCode = %q, want %q", loc.CountryCode, "US")
	}
}

// TestLookupRequestInvalidIPSkipsChain 覆盖非法 IP 在解析阶段直接返回 Unknown：
// getHeader 与 mmdb 都不应被调用。
func TestLookupRequestInvalidIPSkipsChain(t *testing.T) {
	mmdb := &countResolver{}
	withChainState(t, mmdb, []string{"X-Country"})

	headerCalls := 0
	getHeader := func(name string) string {
		headerCalls++
		return "US"
	}

	loc := LookupRequest("not-an-ip", getHeader)
	if loc != Unknown {
		t.Fatalf("LookupRequest(not-an-ip) = %+v, want Unknown", loc)
	}
	if headerCalls != 0 {
		t.Fatalf("getHeader called %d times, want 0 (非法 IP 应直接返回)", headerCalls)
	}
	if got := mmdb.Calls(); got != 0 {
		t.Fatalf("mmdb Lookup called %d times, want 0 (非法 IP 应直接返回)", got)
	}
}

// ============================================================
// 覆盖说明（chain_deep3_test.go 第三轮深测）
// ============================================================
//
// 1. TestLookupRequestIPv6SpecialAddrsLan
//    覆盖 LookupRequest 中 IPv6 特殊地址的 lan 分支：
//    ::1 → IsLoopback；fe80::1 → IsLinkLocalUnicast；ff02::1 → IsMulticast；:: → IsUnspecified。
//    断言四字段均为内网值，验证 lan 的完整构造。
//
// 2. TestLookupRequestLanShortCircuitsChain
//    覆盖 lan 分支的位置：在 header 与 mmdb 之前短路。header 计数器与 mmdb Calls() 都为 0
//    证明 LookupHeader / currentMMDB 均未被触达。
//
// 3. TestLookupRequestBroadcastUnknown
//    覆盖 lan 判定的边界：255.255.255.255 不属于任何 lan 判定分支，且不在内置表中，
//    最终走 return Unknown 分支。
//
// 4. TestLookupRequestMalformedHeaderFallsThrough
//    覆盖 header 命中判定：LookupHeader 对 "USA" 返回 Unknown（3 字母非法），
//    LookupRequest 的 `if loc := LookupHeader(...); loc != Unknown` 不命中，
//    责任链继续走 mmdb，mmdb Calls()==1 证明流量真的穿透到下一级。
//
// 5. TestLookupRequestEnvHeaderNamesEndToEnd
//    覆盖 ReloadFromEnv 读取 LINKSHORT_GEO_HEADERS 并写入 chainHeaderNames 的端到端路径：
//    8.8.8.8 内置表是 US，但 env 配置的头返回 JP，头命中优先，证明 env 配置真正进了责任链。
//    使用 t.Setenv + t.Cleanup 恢复并 ReloadFromEnv 复位，未使用 t.Parallel。
//
// 6. TestLookupRequestBuiltinNilGuard
//    覆盖 LookupRequest 中 `if builtinStatic != nil` 的防御分支：
//    builtinStatic 暂置 nil 后 china 表失效，责任链走到底返回 Unknown。
//    t.Cleanup 恢复原值，保证测试独立可跑。
//
// 7. TestLookupRequestMMDBUnknownFallsToBuiltin
//    覆盖 mmdb 分支的命中判定：fixedResolver 返回 Unknown 时不算命中，
//    责任链继续落到内置表，由 china 表给出 CN/江苏。
//
// 8. TestLookupRequestIPv6ChinaTable
//    覆盖内置表对 IPv6 的处理分支：2400:3200::1 → CN/浙江。
//
// 9. TestLookupRequestTrimsIPForMMDB
//    覆盖 LookupRequest 传给 mmdb 的是 TrimSpace 后的 ip（trimmed）：
//    输入带前后空格的 IP，ipRecordingResolver 收到的应为去空格版本；
//    同时 mmdb 返回 Unknown 后落到内置表得到 US。
//    新类型名 ipRecordingResolver，不重定义 fixedResolver/countResolver。
//
// 10. TestLookupRequestInvalidIPSkipsChain
//     覆盖 LookupRequest 最前面的非法 IP 分支：net.ParseIP 返回 nil 时直接 return Unknown，
//     header 计数器与 mmdb Calls() 都为 0，证明责任链完全未被触发。
