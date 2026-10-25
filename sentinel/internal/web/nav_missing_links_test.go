package web

import (
	"os"
	"strings"
	"testing"
)

func TestIncidentsHasMonitorsLink(t *testing.T) {
	content, err := os.ReadFile("static/incidents.html")
	if err != nil {
		t.Fatalf("read incidents.html: %v", err)
	}
	body := string(content)

	monitors := `<a href="/monitors">监控管理</a>`
	if !strings.Contains(body, monitors) {
		t.Errorf("incidents.html 缺少监控管理链接: %s", monitors)
		return
	}
	overview := `<a href="/">总览</a>`
	incidents := `<a href="/incidents" class="active">事件</a>`
	if strings.Index(body, overview) >= strings.Index(body, monitors) {
		t.Errorf("incidents.html 中总览链接应出现在监控管理链接之前")
	}
	if strings.Index(body, monitors) >= strings.Index(body, incidents) {
		t.Errorf("incidents.html 中监控管理链接应出现在事件链接之前")
	}
}

func TestSmsLogHasMonitorsLink(t *testing.T) {
	content, err := os.ReadFile("static/sms_log.html")
	if err != nil {
		t.Fatalf("read sms_log.html: %v", err)
	}
	body := string(content)

	monitors := `<a href="/monitors">监控管理</a>`
	if !strings.Contains(body, monitors) {
		t.Errorf("sms_log.html 缺少监控管理链接: %s", monitors)
		return
	}
	overview := `<a href="/">总览</a>`
	incidents := `<a href="/incidents">事件</a>`
	if strings.Index(body, overview) >= strings.Index(body, monitors) {
		t.Errorf("sms_log.html 中总览链接应出现在监控管理链接之前")
	}
	if strings.Index(body, monitors) >= strings.Index(body, incidents) {
		t.Errorf("sms_log.html 中监控管理链接应出现在事件链接之前")
	}
}

func TestDeliveriesHasMonitorsAndSmsLinks(t *testing.T) {
	content, err := os.ReadFile("static/deliveries.html")
	if err != nil {
		t.Fatalf("read deliveries.html: %v", err)
	}
	body := string(content)

	monitors := `<a href="/monitors">监控管理</a>`
	if !strings.Contains(body, monitors) {
		t.Errorf("deliveries.html 缺少监控管理链接: %s", monitors)
		return
	}
	smsLog := `<a href="/sms-log">短信记录</a>`
	if !strings.Contains(body, smsLog) {
		t.Errorf("deliveries.html 缺少短信记录链接: %s", smsLog)
		return
	}
	dashboard := `<a href="/">仪表盘</a>`
	incidents := `<a href="/incidents">事件</a>`
	deliveries := `<a href="/deliveries" class="active">投递队列</a>`
	if strings.Index(body, dashboard) >= strings.Index(body, monitors) {
		t.Errorf("deliveries.html 中仪表盘链接应出现在监控管理链接之前")
	}
	if strings.Index(body, monitors) >= strings.Index(body, incidents) {
		t.Errorf("deliveries.html 中监控管理链接应出现在事件链接之前")
	}
	if strings.Index(body, deliveries) >= strings.Index(body, smsLog) {
		t.Errorf("deliveries.html 中投递队列链接应出现在短信记录链接之前")
	}
}
