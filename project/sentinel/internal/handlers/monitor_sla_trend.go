package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleMonitorSLATrendJSON(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	report, err := s.store.MonitorSLATrend(id, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成单监控 SLA 趋势失败")
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (s *Server) handleMonitorSLATrendPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "monitor_sla_trend.html", "text/html; charset=utf-8")
}
func (s *Server) handleMonitorSLATrendHTML(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	rep, err := s.store.MonitorSLATrend(id, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成单监控 SLA 趋势失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderMonitorSLATrendHTML(rep)))
}

func renderMonitorSLATrendHTML(rep store.MonitorSLATrendReport) string {
	var b strings.Builder
	b.WriteString("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>单监控 SLA 趋势 " + html.EscapeString(rep.MonitorName) + " " + rep.EndMonth + "</title></head><body>")
	b.WriteString("<h1>单监控 SLA 趋势 " + html.EscapeString(rep.MonitorName) + " " + rep.EndMonth + "</h1>")
	b.WriteString("<p>" + fmt.Sprintf("最近 %d 个月单监控聚合，目标 99.9%%。", rep.Months) + "</p>")
	b.WriteString("<table><thead><tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>达标</th></tr></thead><tbody>")
	for _, it := range rep.Items {
		b.WriteString("<tr>")
		b.WriteString("<td>" + it.Month + "</td>")
		b.WriteString("<td>" + fmt.Sprintf("%.2f%%", it.UptimePct) + "</td>")
		b.WriteString("<td>" + fmt.Sprintf("%d", it.TotalChecks) + "</td>")
		b.WriteString("<td>" + fmt.Sprintf("%d", it.DownIncidents) + "</td>")
		b.WriteString("<td>" + slaDur(float64(it.TotalDowntimeSec)) + "</td>")
		if it.Met {
			b.WriteString("<td>达标</td>")
		} else {
			b.WriteString("<td>未达标</td>")
		}
		b.WriteString("</tr>")
	}
	b.WriteString("</tbody></table>")
	b.WriteString("<h2>可用性条形</h2>")
	for _, it := range rep.Items {
		pct := fmt.Sprintf("%.2f", it.UptimePct)
		b.WriteString("<div class=\"trend-row\">")
		b.WriteString("<span class=\"trend-month\">" + it.Month + "</span>")
		b.WriteString("<div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:" + pct + "%\"></div></div>")
		b.WriteString("<span class=\"trend-pct\">" + pct + "%</span>")
		b.WriteString("</div>")
	}
	b.WriteString("</body></html>")
	return b.String()
}
