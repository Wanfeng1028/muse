package geo

import "testing"

// TestChinaTableHit 验证内置中国 CIDR 表对常见命中 IP 的解析结果。
func TestChinaTableHit(t *testing.T) {
	tests := []struct {
		name string
		ip   string
		want Location
	}{
		{"浙江223.5.5.5", "223.5.5.5", Location{"CN", "中国", "浙江"}},
		{"浙江223.6.6.6", "223.6.6.6", Location{"CN", "中国", "浙江"}},
		{"江苏114.114.114.114", "114.114.114.114", Location{"CN", "中国", "江苏"}},
		{"江苏114.114.115.115", "114.114.115.115", Location{"CN", "中国", "江苏"}},
		{"广东119.29.29.29", "119.29.29.29", Location{"CN", "中国", "广东"}},
		{"广东182.254.116.116", "182.254.116.116", Location{"CN", "中国", "广东"}},
		{"北京180.76.76.76", "180.76.76.76", Location{"CN", "中国", "北京"}},
		{"北京1.2.4.8", "1.2.4.8", Location{"CN", "中国", "北京"}},
		{"北京210.2.4.8", "210.2.4.8", Location{"CN", "中国", "北京"}},
		{"美国8.8.8.8", "8.8.8.8", Location{"US", "美国", "unknown"}},
		{"美国8.8.4.4", "8.8.4.4", Location{"US", "美国", "unknown"}},
		{"美国1.1.1.1", "1.1.1.1", Location{"US", "美国", "unknown"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := builtinStatic.Lookup(tt.ip)
			if got != tt.want {
				t.Fatalf("Lookup(%q) = %#v, want %#v", tt.ip, got, tt.want)
			}
		})
	}
}

// TestChinaTableMissHonestUnknown 验证未命中或非法输入返回 Unknown，且不 panic。
func TestChinaTableMissHonestUnknown(t *testing.T) {
	tests := []struct {
		name string
		ip   string
	}{
		{"未命中203.0.113.7", "203.0.113.7"},
		{"未命中198.51.100.9", "198.51.100.9"},
		{"空字符串", ""},
		{"非IP字符串", "abc"},
		{"非法IPv4", "999.1.1.1"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := builtinStatic.Lookup(tt.ip)
			if got != Unknown {
				t.Fatalf("Lookup(%q) = %#v, want Unknown %#v", tt.ip, got, Unknown)
			}
		})
	}
}

// TestChinaTableIPv6 验证内置表对 IPv6 CIDR 的解析结果。
func TestChinaTableIPv6(t *testing.T) {
	got := builtinStatic.Lookup("2400:3200::1")
	want := Location{"CN", "中国", "浙江"}
	if got != want {
		t.Fatalf("Lookup(%q) = %#v, want %#v", "2400:3200::1", got, want)
	}
}

// TestBuiltinStaticInjected 验证 init 已注入非空的 builtinStatic 解析器。
func TestBuiltinStaticInjected(t *testing.T) {
	if builtinStatic == nil {
		t.Fatal("builtinStatic 不应为 nil")
	}

	got := builtinStatic.Lookup("223.5.5.5")
	if got == Unknown {
		t.Fatalf("builtinStatic.Lookup(%q) 不应返回 Unknown", "223.5.5.5")
	}
}
