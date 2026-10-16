package geo

import "testing"

func TestLookupHeader(t *testing.T) {
	tests := []struct {
		name  string
		get   func(name string) string
		names []string
		want  Location
	}{
		{
			name:  "国家码带省份",
			get:   func(name string) string { return "us:California" },
			names: []string{"X-Test"},
			want:  Location{CountryCode: "US", CountryName: "美国", Province: "California"},
		},
		{
			name:  "仅国家码",
			get:   func(name string) string { return "JP" },
			names: []string{"X-Test"},
			want:  Location{CountryCode: "JP", CountryName: "日本", Province: "unknown"},
		},
		{
			name:  "未收录国家码",
			get:   func(name string) string { return "XX" },
			names: []string{"X-Test"},
			want:  Location{CountryCode: "XX", CountryName: "XX", Province: "unknown"},
		},
		{
			name:  "国家码长度非法",
			get:   func(name string) string { return "toolong" },
			names: []string{"X-Test"},
			want:  Unknown,
		},
		{
			name:  "请求头为空",
			get:   func(name string) string { return "" },
			names: []string{"X-Test"},
			want:  Unknown,
		},
		{
			name:  "get 为 nil",
			get:   nil,
			names: []string{"X-Test"},
			want:  Unknown,
		},
		{
			name: "按顺序找到第一个非空请求头",
			get: func(name string) string {
				headers := map[string]string{
					"X-First":  "",
					"X-Second": "CN:浙江",
				}
				return headers[name]
			},
			names: []string{"X-First", "X-Second"},
			want:  Location{CountryCode: "CN", CountryName: "中国", Province: "浙江"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := LookupHeader(tt.get, tt.names)
			if got != tt.want {
				t.Errorf("LookupHeader() = %#v, want %#v", got, tt.want)
			}
		})
	}
}

func TestHeaderNames(t *testing.T) {
	t.Setenv("LINKSHORT_GEO_HEADERS", "")
	got := HeaderNames()
	want := []string{"X-Region", "X-Country-Code", "CF-IPCountry", "X-Client-Country"}
	if len(got) != len(want) {
		t.Fatalf("HeaderNames() = %#v, want %#v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("HeaderNames() = %#v, want %#v", got, want)
		}
	}

	t.Setenv("LINKSHORT_GEO_HEADERS", "X-A, X-B")
	got = HeaderNames()
	want = []string{"X-A", "X-B"}
	if len(got) != len(want) {
		t.Fatalf("HeaderNames() = %#v, want %#v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("HeaderNames() = %#v, want %#v", got, want)
		}
	}
}
