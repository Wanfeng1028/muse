package handlers

import (
	"fmt"
	"html"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"sentinel/internal/store"
)

// snapshotItem 是渲染快照所需的单个 monitor 视图数据。
type snapshotItem struct {
	Name        string
	Status      string // up / down / unknown
	Uptime30    float64
	LastChecked string
	LatencyMs   int64
	Daily       []store.DayStat
}

var hexColorRe = regexp.MustCompile(`^#[0-9a-fA-F]{6}$`)

// handleStatusPageSnapshot 生成状态页单文件静态 HTML 快照并作为附件下载。
func (s *Server) handleStatusPageSnapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok || id <= 0 {
		return
	}

	page, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}

	monitors, err := s.store.ListPageMonitors(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}

	items := make([]snapshotItem, 0, len(monitors))
	for _, m := range monitors {
		it := snapshotItem{
			Name:        m.Name,
			Status:      "unknown",
			LastChecked: "无数据",
			LatencyMs:   0,
		}
		if lc, err := s.store.LastCheck(m.ID); err == nil && lc != nil {
			if lc.Ok == 1 {
				it.Status = "up"
			} else {
				it.Status = "down"
			}
			it.LastChecked = lc.CheckedAt
			it.LatencyMs = lc.LatencyMs
		}
		if up, _, _, _, err := s.store.MonitorStats(m.ID, 30); err == nil {
			it.Uptime30 = up
		} else {
			it.Uptime30 = 100
		}
		if daily, err := s.store.DailyBreakdown(m.ID, 90); err == nil {
			it.Daily = daily
		}
		items = append(items, it)
	}

	body := renderSnapshotHTML(page, items)

	filename := fmt.Sprintf("status-%s-%s.html", page.Slug, time.Now().UTC().Format("20060102"))
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

// renderSnapshotHTML 拼出完整 HTML 文档；左对齐信息密集运维风格，全部内联无外部资源。
func renderSnapshotHTML(page store.StatusPage, items []snapshotItem) string {
	dark := page.Theme == "dark"
	accent := ""
	if hexColorRe.MatchString(page.AccentColor) {
		accent = page.AccentColor
	}

	var b strings.Builder
	b.WriteString("<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n")
	b.WriteString("<meta charset=\"utf-8\">\n")
	b.WriteString("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
	b.WriteString("<title>" + html.EscapeString(page.Title) + "</title>\n")
	b.WriteString("<style>\n")
	b.WriteString(snapshotCSS(dark, accent))
	b.WriteString("</style>\n</head>\n<body>\n")
	b.WriteString("<div class=\"wrap\">\n")
	b.WriteString("<h1>" + html.EscapeString(page.Title) + "</h1>\n")
	b.WriteString("<div class=\"banner\">" + html.EscapeString(bannerText(items)) + "</div>\n")

	for _, it := range items {
		b.WriteString("<section class=\"card\">\n")
		b.WriteString("<div class=\"card-head\"><span class=\"mname\">" + html.EscapeString(it.Name) + "</span>")
		b.WriteString(statusPill(it.Status))
		b.WriteString("</div>\n")
		b.WriteString("<div class=\"meta\">")
		b.WriteString("<span>30 天可用性 " + formatPct(it.Uptime30) + "</span>")
		b.WriteString("<span>最近检查 " + html.EscapeString(it.LastChecked) + "</span>")
		b.WriteString("<span>延迟 " + strconv.FormatInt(it.LatencyMs, 10) + " ms</span>")
		b.WriteString("</div>\n")
		b.WriteString("<div class=\"bars\">")
		for _, d := range it.Daily {
			b.WriteString(dailyBar(d))
		}
		b.WriteString("</div>\n")
		b.WriteString("</section>\n")
	}

	b.WriteString("</div>\n</body>\n</html>\n")
	return b.String()
}

// bannerText 依据整体状态给出顶部总览文案。
func bannerText(items []snapshotItem) string {
	down := 0
	unknown := 0
	for _, it := range items {
		switch it.Status {
		case "down":
			down++
		case "unknown":
			unknown++
		}
	}
	if down > 0 {
		return strconv.Itoa(down) + " 个服务异常"
	}
	if unknown > 0 {
		return "部分服务状态未知"
	}
	return "全部服务正常"
}

// statusPill 输出圆点加文字的状态标签，避免使用图标字体或 emoji。
func statusPill(status string) string {
	label := "未知"
	cls := "unknown"
	switch status {
	case "up":
		label = "正常"
		cls = "up"
	case "down":
		label = "故障"
		cls = "down"
	}
	return "<span class=\"pill " + cls + "\"><i class=\"dot\"></i>" + label + "</span>"
}

// dailyBar 生成单日竖条，颜色按可用性分档，无检查天为浅灰。
func dailyBar(d store.DayStat) string {
	color := "#e5e7eb"
	title := d.Date + " 无检查"
	if d.Checks > 0 {
		switch {
		case d.UptimePct >= 99.9:
			color = "#16a34a"
		case d.UptimePct >= 99:
			color = "#d97706"
		default:
			color = "#dc2626"
		}
		title = d.Date + " " + formatPct(d.UptimePct)
	}
	return "<span class=\"bar\" data-day=\"" + html.EscapeString(d.Date) + "\" title=\"" +
		html.EscapeString(title) + "\" style=\"background:" + color + "\"></span>"
}

// formatPct 统一保留两位小数并去掉多余零，保持紧凑。
func formatPct(v float64) string {
	s := strconv.FormatFloat(v, 'f', 2, 64)
	return s + "%"
}

// snapshotCSS 生成内联样式表，主题与强调色在生成期决定，运行时不依赖任何外部资源。
func snapshotCSS(dark bool, accent string) string {
	bg := "#ffffff"
	fg := "#111827"
	card := "#f9fafb"
	border := "#e5e7eb"
	muted := "#6b7280"
	if dark {
		bg = "#0f172a"
		fg = "#e2e8f0"
		card = "#1e293b"
		border = "#334155"
		muted = "#94a3b8"
	}
	titleColor := fg
	if accent != "" {
		titleColor = accent
	}

	var b strings.Builder
	b.WriteString("*{box-sizing:border-box}\n")
	b.WriteString("body{margin:0;background:" + bg + ";color:" + fg + ";" +
		"font-family:-apple-system,\"PingFang SC\",\"Microsoft YaHei\",sans-serif;" +
		"font-size:14px;line-height:1.5}\n")
	b.WriteString(".wrap{max-width:880px;margin:0;padding:24px 20px 48px;text-align:left}\n")
	b.WriteString("h1{margin:0 0 12px;font-size:20px;font-weight:600;text-align:left;color:" + titleColor + "}\n")
	b.WriteString(".banner{padding:10px 14px;border:1px solid " + border + ";border-radius:6px;" +
		"background:" + card + ";margin-bottom:20px}\n")
	b.WriteString(".card{border:1px solid " + border + ";border-radius:6px;background:" + card + ";" +
		"padding:14px 16px;margin-bottom:14px}\n")
	b.WriteString(".card-head{display:flex;align-items:center;justify-content:flex-start;gap:10px;" +
		"margin-bottom:8px}\n")
	b.WriteString(".mname{font-weight:600;font-size:15px}\n")
	b.WriteString(".pill{display:inline-flex;align-items:center;gap:5px;font-size:12px;" +
		"padding:2px 8px;border-radius:10px;border:1px solid " + border + "}\n")
	b.WriteString(".dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:" + muted + "}\n")
	b.WriteString(".pill.up .dot{background:#16a34a}\n")
	b.WriteString(".pill.down .dot{background:#dc2626}\n")
	b.WriteString(".pill.unknown .dot{background:" + muted + "}\n")
	b.WriteString(".meta{display:flex;flex-wrap:wrap;gap:16px;color:" + muted + ";font-size:12px;" +
		"margin-bottom:10px}\n")
	b.WriteString(".bars{display:flex;align-items:flex-end;gap:2px;height:28px}\n")
	b.WriteString(".bar{flex:1 1 0;min-width:2px;height:100%;border-radius:1px}\n")
	return b.String()
}
