package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleGroupYearlySLAJSON(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	year, perr := parseSiteYearlySLAParams(r)
	if perr != "" {
		writeErr(w, http.StatusBadRequest, perr)
		return
	}
	rep, err := s.store.GroupYearlySLA(id, year)
	if err != nil && err.Error() == "分组不存在" {
		writeErr(w, http.StatusNotFound, "分组不存在")
		return
	}
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成分组年度 SLA 失败")
		return
	}
	writeJSON(w, http.StatusOK, rep)
}

func (s *Server) handleGroupYearlySLAHTML(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}
	year, perr := parseSiteYearlySLAParams(r)
	if perr != "" {
		writeErr(w, http.StatusBadRequest, perr)
		return
	}
	rep, err := s.store.GroupYearlySLA(id, year)
	if err != nil && err.Error() == "分组不存在" {
		writeErr(w, http.StatusNotFound, "分组不存在")
		return
	}
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成分组年度 SLA 失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	w.Write([]byte(renderGroupYearlySLAHTML(rep)))
}

func (s *Server) handleGroupYearlySLAPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "group_sla_year.html", "text/html; charset=utf-8")
}

func renderGroupYearlySLAHTML(rep store.GroupYearlySLAReport) string {
	var b strings.Builder
	title := fmt.Sprintf("分组年度 SLA 报告 %s %d", rep.GroupName, rep.Year)
	b.WriteString("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>" + html.EscapeString(title) + "</title></head><body>")
	b.WriteString("<h1>" + html.EscapeString(title) + "</h1>")
	b.WriteString("<p>全年聚合，目标 99.9%，只统计组内监控。</p>")
	status := "未达标"
	if rep.Met {
		status = "达标"
	}
	b.WriteString(fmt.Sprintf("<p>年度可用性：%.2f%%，检查总数：%d，最佳月份：%s，最差月份：%s，是否达标：%s。</p>",
		rep.UptimePct, rep.TotalChecks, html.EscapeString(rep.BestMonth), html.EscapeString(rep.WorstMonth), status))
	b.WriteString("<table><tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>监控数</th><th>最差监控</th><th>达标</th></tr>")
	for _, it := range rep.Items {
		met := "未达标"
		if it.Met {
			met = "达标"
		}
		b.WriteString(fmt.Sprintf("<tr><td>%s</td><td>%.2f%%</td><td>%d</td><td>%d</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td></tr>",
			html.EscapeString(it.Month), it.UptimePct, it.TotalChecks, it.DownIncidents, slaDur(float64(it.TotalDowntimeSec)), it.MonitorCount, html.EscapeString(it.WorstMonitorName), met))
	}
	b.WriteString("</table><h2>可用性条形</h2>")
	for _, it := range rep.Items {
		b.WriteString(fmt.Sprintf("<div class=\"trend-row\"><span class=\"trend-month\">%s</span><div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:%.2f%%\"></div></div><span class=\"trend-pct\">%.2f%%</span></div>",
			html.EscapeString(it.Month), it.UptimePct, it.UptimePct))
	}
	b.WriteString("</body></html>")
	return b.String()
}
