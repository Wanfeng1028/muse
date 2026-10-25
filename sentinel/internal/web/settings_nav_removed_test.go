package web

import (
	"io/fs"
	"strings"
	"testing"
)

func TestDeadSettingsNavRemoved(t *testing.T) {
	tests := []struct {
		file   string
		active string
	}{
		{"static/incidents.html", `<a href="/incidents" class="active">事件</a>`},
		{"static/sms_log.html", `<a href="/sms-log" class="active">短信记录</a>`},
		{"static/deliveries.html", `<a href="/deliveries" class="active">投递队列</a>`},
	}

	for _, tt := range tests {
		t.Run(tt.file, func(t *testing.T) {
			data, err := fs.ReadFile(FS, tt.file)
			if err != nil {
				t.Fatalf("read %s: %v", tt.file, err)
			}
			content := string(data)

			if strings.Contains(content, "/settings") {
				t.Errorf("%s still contains dead link \"/settings\"", tt.file)
			}

			if !strings.Contains(content, tt.active) {
				t.Errorf("%s missing active nav marker %q", tt.file, tt.active)
			}
		})
	}
}
