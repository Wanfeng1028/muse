package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestMonitorsNavLinks(t *testing.T) {
	data, err := fs.ReadFile(FS, "static/monitors.html")
	if err != nil {
		t.Fatalf("read monitors.html: %v", err)
	}
	h := string(data)
	for _, m := range []string{
		`<a href="/">总览</a>`,
		`<a href="/monitors" class="active">监控管理</a>`,
		`<a href="/incidents">事件</a>`,
		`<a href="/deliveries">投递队列</a>`,
		`<a href="/sms-log">短信记录</a>`,
	} {
		if !strings.Contains(h, m) {
			t.Errorf("monitors.html: missing marker: %s", m)
		}
	}
	for _, d := range []string{"/index.html", "/monitors.html", "/alerts.html", "/settings.html"} {
		if strings.Contains(h, d) {
			t.Errorf("monitors.html: dead nav link: %s", d)
		}
	}
}
