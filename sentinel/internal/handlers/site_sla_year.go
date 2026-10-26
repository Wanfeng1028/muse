package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strconv"
	"strings"
	"time"

	"sentinel/internal/store"
)

func parseSiteYearlySLAParams(r *http.Request) (int, string) {
	yearStr := r.URL.Query().Get("year")
	if yearStr == "" {
		return time.Now().UTC().Year(), ""
	}
	year, err := strconv.Atoi(yearStr)
	if err != nil || year < 1970 || year > 9999 {
		return 0, "year 参数非法"
	}
	return year, ""
}

func (s *Server) handleSiteYearlySLAJSON(w http.ResponseWriter, r *http.Request) {
	year, errMsg := parseSiteYearlySLAParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	report, err := s.store.SiteYearlySLA(year)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站年度 SLA 失败")
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func renderSiteYearlySLAHTML(rep store.SiteYearlySLAReport) string {
	var b strings.Builder
	title := fmt.Sprintf("全站年度 SLA 报告 %d", rep.Year)
	fmt.Fprintf(&b, "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n<title>%s</title>\n</head>\n<body>\n", title)
	fmt.Fprintf(&b, "<h1>%s</h1>\n", title)
	b.WriteString("<p>全年聚合，目标 99.9%。</p>\n")
	yearMet := "未达标"
	if rep.Met {
		yearMet = "达标"
	}
	fmt.Fprintf(&b, "<p>年度可用性：%.2f%%，检查总数：%d，最佳月份：%s，最差月份：%s，是否达标：%s</p>\n", rep.UptimePct, rep.TotalChecks, rep.BestMonth, rep.WorstMonth, yearMet)
	b.WriteString("<table>\n<thead>\n<tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>监控数</th><th>最差监控</th><th>达标</th></tr>\n</thead>\n<tbody>\n")
	for _, it := range rep.Items {
		met := "未达标"
		if it.Met {
			met = "达标"
		}
		fmt.Fprintf(&b, "<tr><td>%s</td><td>%.2f%%</td><td>%d</td><td>%d</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td></tr>\n", it.Month, it.UptimePct, it.TotalChecks, it.DownIncidents, slaDur(float64(it.TotalDowntimeSec)), it.MonitorCount, html.EscapeString(it.WorstMonitorName), met)
	}
	b.WriteString("</tbody>\n</table>\n")
	b.WriteString("<h2>可用性条形</h2>\n")
	for _, it := range rep.Items {
		fmt.Fprintf(&b, "<div class=\"trend-row\"><span class=\"trend-month\">%s</span><div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:%.2f%%\"></div></div><span class=\"trend-pct\">%.2f%%</span></div>\n", it.Month, it.UptimePct, it.UptimePct)
	}
	b.WriteString("</body>\n</html>")
	return b.String()
}

func (s *Server) handleSiteYearlySLAHTML(w http.ResponseWriter, r *http.Request) {
	year, errMsg := parseSiteYearlySLAParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	rep, err := s.store.SiteYearlySLA(year)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站年度 SLA 失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderSiteYearlySLAHTML(rep)))
}

func (s *Server) handleSiteYearlySLAPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "sla_year.html", "text/html; charset=utf-8")
}
