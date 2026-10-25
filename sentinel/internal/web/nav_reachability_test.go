package web

import (
	"os"
	"strings"
	"testing"
)

func TestNavSnapshotsLinkOnFourPages(t *testing.T) {
	pages := []string{"static/monitors.html", "static/incidents.html", "static/deliveries.html", "static/sms_log.html"}
	for _, page := range pages {
		content, err := os.ReadFile(page)
		if err != nil {
			t.Fatalf("read %s: %v", page, err)
		}
		body := string(content)
		if !strings.Contains(body, `<a href="/snapshots">快照归档</a>`) {
			t.Errorf("%s 缺少快照归档导航链接", page)
		}
	}
}

func TestNavSmsLinkOnIndexAndSnapshots(t *testing.T) {
	pages := []string{"static/index.html", "static/snapshots.html"}
	for _, page := range pages {
		content, err := os.ReadFile(page)
		if err != nil {
			t.Fatalf("read %s: %v", page, err)
		}
		body := string(content)
		if !strings.Contains(body, `<a href="/sms-log">短信记录</a>`) {
			t.Errorf("%s 缺少短信记录导航链接", page)
		}
	}
}

func TestNavProfileHasBothLinks(t *testing.T) {
	content, err := os.ReadFile("static/profile.html")
	if err != nil {
		t.Fatalf("read profile.html: %v", err)
	}
	body := string(content)

	smsLink := `<a href="/sms-log">短信记录</a>`
	snapLink := `<a href="/snapshots">快照归档</a>`
	deliveryLink := `<a href="/deliveries">投递队列</a>`

	if !strings.Contains(body, smsLink) {
		t.Errorf("profile.html 缺少短信记录导航链接")
	}
	if !strings.Contains(body, snapLink) {
		t.Errorf("profile.html 缺少快照归档导航链接")
	}

	smsIdx := strings.Index(body, smsLink)
	snapIdx := strings.Index(body, snapLink)
	deliveryIdx := strings.Index(body, deliveryLink)
	if deliveryIdx == -1 {
		t.Errorf("profile.html 缺少投递队列导航链接，无法比较顺序")
	} else if !(smsIdx > deliveryIdx && snapIdx > smsIdx) {
		t.Errorf("profile.html 导航链接顺序错误：投递队列=%d，短信记录=%d，快照归档=%d", deliveryIdx, smsIdx, snapIdx)
	}
}
