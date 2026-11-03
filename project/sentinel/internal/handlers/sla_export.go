package handlers

import (
	"bytes"
	"fmt"
	"html"
	"net/http"
	"sort"
	"strconv"
	"time"

	"sentinel/internal/store"
)

func (s *Server) handleMonitorSLAHTML(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	m, err := s.store.GetMonitor(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "监控不存在")
		return
	}
	month := r.URL.Query().Get("month")
	if month == "" {
		month = time.Now().UTC().Format("2006-01")
	}
	if len(month) != 7 || month[4] != '-' {
		writeErr(w, http.StatusBadRequest, "month 格式应为 YYYY-MM")
		return
	}
	y, err1 := strconv.Atoi(month[0:4])
	mo, err2 := strconv.Atoi(month[5:7])
	if err1 != nil || err2 != nil || y < 1970 || y > 9999 || mo < 1 || mo > 12 {
		writeErr(w, http.StatusBadRequest, "month 格式应为 YYYY-MM")
		return
	}
	rep, err := s.store.MonthlySLA(id, y, mo)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成 SLA 报告失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderSLAHTML(m.Name, rep)))
}

func slaDur(sec float64) string {
	if sec < 0 {
		sec = 0
	}
	total := int64(sec)
	if total < 60 {
		return fmt.Sprintf("%d 秒", total)
	}
	days := total / 86400
	hours := (total % 86400) / 3600
	mins := (total % 3600) / 60
	if days > 0 {
		return fmt.Sprintf("%d 天 %d 小时 %d 分钟", days, hours, mins)
	}
	if hours > 0 {
		return fmt.Sprintf("%d 小时 %d 分钟", hours, mins)
	}
	return fmt.Sprintf("%d 分钟", mins)
}

func attribName(key string) string {
	switch key {
	case "timeout":
		return "超时"
	case "dns":
		return "DNS 解析"
	case "connection":
		return "连接失败"
	case "cert":
		return "证书问题"
	case "keyword":
		return "关键字断言"
	case "http_5xx":
		return "服务端 5xx"
	case "other":
		return "其他"
	default:
		return key
	}
}

func renderSLAHTML(monitorName string, rep store.SLAReport) string {
	var b bytes.Buffer
	badge := `<span style="display:inline-block;padding:2px 10px;border-radius:10px;background:#dc2626;color:#fff;font-size:12px;">未达标</span>`
	if rep.Met {
		badge = `<span style="display:inline-block;padding:2px 10px;border-radius:10px;background:#16a34a;color:#fff;font-size:12px;">达标</span>`
	}
	b.WriteString(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>`)
	b.WriteString(html.EscapeString(monitorName))
	b.WriteString(` · 月度 SLA 报告</title></head><body style="margin:0;padding:24px;background:#f6f7f9;color:#1f2937;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.6;">`)
	b.WriteString(`<div style="max-width:720px;margin:0 auto;">`)

	b.WriteString(`<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:20px 24px;margin-bottom:16px;">`)
	b.WriteString(`<h1 style="margin:0 0 8px 0;font-size:18px;font-weight:600;color:#1f2937;">`)
	b.WriteString(html.EscapeString(monitorName))
	b.WriteString(` · 月度 SLA 报告（`)
	b.WriteString(html.EscapeString(rep.Month))
	b.WriteString(`）</h1>`)
	b.WriteString(`<div style="margin-top:4px;">`)
	b.WriteString(badge)
	b.WriteString(`</div></div>`)

	b.WriteString(`<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:20px 24px;margin-bottom:16px;">`)
	b.WriteString(`<h2 style="margin:0 0 12px 0;font-size:15px;font-weight:600;color:#1f2937;">指标</h2>`)
	b.WriteString(`<table style="width:100%;border-collapse:collapse;">`)
	row := func(k, v string) {
		b.WriteString(`<tr><td style="padding:6px 0;color:#6b7280;width:180px;">`)
		b.WriteString(html.EscapeString(k))
		b.WriteString(`</td><td style="padding:6px 0;color:#1f2937;">`)
		b.WriteString(html.EscapeString(v))
		b.WriteString(`</td></tr>`)
	}
	row("可用性", formatPct(rep.UptimePct))
	row("检查次数", strconv.Itoa(rep.TotalChecks))
	row("宕机事件数", strconv.Itoa(rep.DownIncidents))
	row("总宕机时长", slaDur(float64(rep.TotalDowntimeSec)))
	row("MTTR", slaDur(rep.MTTRSec))
	row("SLA 目标", formatPct(rep.Target))
	row("未关闭事件数", strconv.Itoa(rep.OpenIncidents))
	b.WriteString(`</table></div>`)

	b.WriteString(`<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:20px 24px;margin-bottom:16px;">`)
	b.WriteString(`<h2 style="margin:0 0 12px 0;font-size:15px;font-weight:600;color:#1f2937;">严重分级</h2>`)
	b.WriteString(`<table style="width:100%;border-collapse:collapse;">`)
	row("P1", strconv.Itoa(rep.Severity.P1))
	row("P2", strconv.Itoa(rep.Severity.P2))
	row("P3", strconv.Itoa(rep.Severity.P3))
	b.WriteString(`</table></div>`)

	b.WriteString(`<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:20px 24px;margin-bottom:16px;">`)
	b.WriteString(`<h2 style="margin:0 0 12px 0;font-size:15px;font-weight:600;color:#1f2937;">故障归因</h2>`)
	keys := make([]string, 0, len(rep.Attribution))
	for k := range rep.Attribution {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	if len(keys) == 0 {
		b.WriteString(`<div style="color:#6b7280;">暂无数据</div>`)
	} else {
		b.WriteString(`<table style="width:100%;border-collapse:collapse;">`)
		for _, k := range keys {
			cnt := rep.Attribution[k]
			pct := rep.AttributionPct[k]
			width := pct
			if width < 0 {
				width = 0
			}
			if width > 100 {
				width = 100
			}
			b.WriteString(`<tr><td style="padding:6px 8px 6px 0;color:#1f2937;width:130px;vertical-align:top;">`)
			b.WriteString(html.EscapeString(attribName(k)))
			b.WriteString(`</td><td style="padding:6px 8px 6px 0;color:#1f2937;width:60px;vertical-align:top;">`)
			b.WriteString(strconv.Itoa(cnt))
			b.WriteString(`</td><td style="padding:6px 8px 6px 0;color:#6b7280;width:64px;vertical-align:top;">`)
			b.WriteString(html.EscapeString(fmt.Sprintf("%.1f%%", pct)))
			b.WriteString(`</td><td style="padding:6px 0;vertical-align:middle;">`)
			b.WriteString(`<div style="background:#e5e7eb;border-radius:4px;height:10px;width:100%;overflow:hidden;"><div style="background:#10b981;height:10px;width:`)
			b.WriteString(strconv.FormatFloat(width, 'f', 1, 64))
			b.WriteString(`%;"></div></div></td></tr>`)
		}
		b.WriteString(`</table>`)
	}
	b.WriteString(`</div>`)

	b.WriteString(`<div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:20px 24px;color:#6b7280;font-size:12px;">`)
	b.WriteString(`<div>事件按 started_at 归属月份</div>`)
	b.WriteString(`<div>无检查月份可用性记 100</div>`)
	b.WriteString(`<div>未关闭事件按查询时刻估算，不写回数据库</div>`)
	b.WriteString(`</div>`)

	b.WriteString(`</div></body></html>`)
	return b.String()
}
