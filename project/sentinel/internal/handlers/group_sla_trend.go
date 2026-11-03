package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleGroupSLATrendJSON(w http.ResponseWriter, r *http.Request) {
	groupID, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	report, err := s.store.GroupSLATrend(groupID, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "分组不存在" {
			writeErr(w, http.StatusNotFound, "分组不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成分组 SLA 趋势失败")
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (s *Server) handleGroupSLATrendPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "group_sla_trend.html", "text/html; charset=utf-8")
}
func (s *Server) handleGroupSLATrendHTML(w http.ResponseWriter, r *http.Request) {
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
	rep, err := s.store.GroupSLATrend(id, endYear, endMonth, months)
	if err != nil {
		if err.Error() == "分组不存在" {
			writeErr(w, http.StatusNotFound, "分组不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成分组 SLA 趋势失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderGroupSLATrendHTML(rep)))
}

func renderGroupSLATrendHTML(rep store.GroupSLATrendReport) string {
	var b strings.Builder
	b.WriteString("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>分组 SLA 趋势 " + html.EscapeString(rep.GroupName) + " " + rep.EndMonth + "</title></head><body>")
	b.WriteString("<h1>分组 SLA 趋势 " + html.EscapeString(rep.GroupName) + " " + rep.EndMonth + "</h1>")
	b.WriteString(fmt.Sprintf("<p>最近 %d 个月分组聚合，目标 99.9%%。</p>", rep.Months))
	b.WriteString("<h2>逐月</h2>")
	b.WriteString("<table><tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>监控数</th><th>最差监控</th><th>达标</th></tr>")
	for _, it := range rep.Items {
		met := "未达标"
		if it.Met {
			met = "达标"
		}
		fmt.Fprintf(&b, "<tr><td>%s</td><td>%.2f%%</td><td>%d</td><td>%d</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td></tr>", it.Month, it.UptimePct, it.TotalChecks, it.DownIncidents, slaDur(float64(it.TotalDowntimeSec)), it.MonitorCount, html.EscapeString(it.WorstMonitorName), met)
	}
	b.WriteString("</table>")
	b.WriteString("<h2>可用性条形</h2>")
	for _, it := range rep.Items {
		pct := fmt.Sprintf("%.2f", it.UptimePct)
		b.WriteString("<div class=\"trend-row\"><span class=\"trend-month\">" + it.Month + "</span><div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:" + pct + "%\"></div></div><span class=\"trend-pct\">" + pct + "%</span></div>")
	}
	b.WriteString("</body></html>")
	return b.String()
}
