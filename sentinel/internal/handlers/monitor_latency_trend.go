package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleMonitorLatencyTrendJSON(w http.ResponseWriter, r *http.Request) {
	monitorID, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}

	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	report, err := s.store.MonitorLatencyTrend(monitorID, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
		} else {
			writeErr(w, http.StatusInternalServerError, "生成单监控延迟趋势失败")
		}
		return
	}

	writeJSON(w, http.StatusOK, report)
}

func (s *Server) handleMonitorLatencyTrendPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "monitor_latency_trend.html", "text/html; charset=utf-8")
}

func (s *Server) handleMonitorLatencyTrendHTML(w http.ResponseWriter, r *http.Request) {
	monitorID, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}

	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	rep, err := s.store.MonitorLatencyTrend(monitorID, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
		} else {
			writeErr(w, http.StatusInternalServerError, "生成单监控延迟趋势失败")
		}
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderMonitorLatencyTrendHTML(rep)))
}

func renderMonitorLatencyTrendHTML(rep store.MonitorLatencyTrendReport) string {
	var b strings.Builder

	b.WriteString("<!DOCTYPE html>\n")
	b.WriteString("<html lang=\"zh-CN\">\n")
	b.WriteString("<head>\n")
	b.WriteString("<meta charset=\"utf-8\">\n")
	b.WriteString("<title>单监控延迟趋势 " + html.EscapeString(rep.MonitorName) + " " + rep.EndMonth + "</title>\n")
	b.WriteString("<style>\n")
	b.WriteString("body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif; margin: 24px; color: #24292f; }\n")
	b.WriteString("h1 { font-size: 22px; margin: 0 0 8px; }\n")
	b.WriteString("p { color: #57606a; margin: 0 0 16px; font-size: 14px; }\n")
	b.WriteString("table { border-collapse: collapse; width: 100%; max-width: 960px; font-size: 14px; }\n")
	b.WriteString("th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: right; }\n")
	b.WriteString("th { background: #f6f8fa; }\n")
	b.WriteString("th:first-child, td:first-child { text-align: left; }\n")
	b.WriteString("h2 { font-size: 18px; margin: 24px 0 12px; }\n")
	b.WriteString(".trend-row { display: flex; align-items: center; margin: 4px 0; max-width: 960px; }\n")
	b.WriteString(".trend-month { width: 80px; flex: none; font-size: 13px; color: #57606a; }\n")
	b.WriteString(".trend-bar { flex: 1; background: #eaeef2; border-radius: 3px; height: 16px; overflow: hidden; }\n")
	b.WriteString(".trend-fill { height: 100%; background: #2f81f7; }\n")
	b.WriteString(".trend-pct { width: 84px; flex: none; text-align: right; font-size: 13px; }\n")
	b.WriteString("</style>\n")
	b.WriteString("</head>\n")
	b.WriteString("<body>\n")

	b.WriteString("<h1>单监控延迟趋势 " + html.EscapeString(rep.MonitorName) + " " + rep.EndMonth + "</h1>\n")
	fmt.Fprintf(&b, "<p>最近 %d 个月单监控成功检查延迟聚合，仅统计成功检查，失败检查不计入分位与均值。</p>\n", rep.Months)

	b.WriteString("<table>\n")
	b.WriteString("<thead><tr><th>月份</th><th>p50 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>平均 (ms)</th><th>成功检查数</th></tr></thead>\n")
	b.WriteString("<tbody>\n")
	for _, it := range rep.Items {
		fmt.Fprintf(&b, "<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%d</td></tr>\n",
			html.EscapeString(it.Month), it.P50Ms, it.P95Ms, it.P99Ms, it.AvgMs, it.TotalChecks)
	}
	b.WriteString("</tbody>\n")
	b.WriteString("</table>\n")

	b.WriteString("<h2>p95 延迟条形</h2>\n")
	if len(rep.Items) == 0 {
		b.WriteString("<p>暂无数据</p>\n")
	} else {
		maxP95 := 0.0
		for _, it := range rep.Items {
			if it.P95Ms > maxP95 {
				maxP95 = it.P95Ms
			}
		}
		for _, it := range rep.Items {
			width := 0.0
			if maxP95 > 0 {
				width = it.P95Ms / maxP95 * 100
			}
			fmt.Fprintf(&b, "<div class=\"trend-row\"><span class=\"trend-month\">%s</span><div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:%.2f%%\"></div></div><span class=\"trend-pct\">%.2f ms</span></div>\n",
				html.EscapeString(it.Month), width, it.P95Ms)
		}
	}

	b.WriteString("</body>\n")
	b.WriteString("</html>\n")

	return b.String()
}
