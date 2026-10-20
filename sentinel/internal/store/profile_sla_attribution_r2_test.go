package store

import "testing"

func TestR2_ClassifyPriority(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{"keyword first", "关键字断言失败：响应体不包含关键字", "keyword"},
		{"cert chinese", "证书将于 3 天后过期，低于预警阈值", "cert"},
		{"cert over timeout", "证书 TLS: handshake timeout", "cert"},
		{"dns no such host", "dial tcp: lookup x: no such host", "dns"},
		{"dns over connection", "connection refused: no such host", "dns"},
		{"connection", "connect: network is unreachable", "connection"},
		{"timeout io", "i/o timeout", "timeout"},
		{"timeout deadline", "context deadline exceeded", "timeout"},
		{"empty", "", "other"},
		{"unknown", "未知错误 boom", "other"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ClassifyFailureCause(tt.input); got != tt.want {
				t.Errorf("ClassifyFailureCause(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

func TestR2_ClassifyHttp5xx(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{"http 503", "状态码不符: 期望 200, 实际 503", "http_5xx"},
		{"http 599", "状态码不符: 期望 200, 实际 599", "http_5xx"},
		{"http 404 is other", "状态码不符: 期望 200, 实际 404", "other"},
		{"http 500", "状态码不符: 期望 200, 实际 500", "http_5xx"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ClassifyFailureCause(tt.input); got != tt.want {
				t.Errorf("ClassifyFailureCause(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}
