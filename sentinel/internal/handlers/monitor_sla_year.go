package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleMonitorYearlySLAJSON(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}

	year, errMsg := parseSiteYearlySLAParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	rep, err := s.store.MonitorYearlySLA(id, year)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成单监控年度 SLA 失败")
		return
	}

	writeJSON(w, http.StatusOK, rep)
}

func (s *Server) handleMonitorYearlySLAHTML(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
		return
	}

	year, errMsg := parseSiteYearlySLAParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	rep, err := s.store.MonitorYearlySLA(id, year)
	if err != nil {
		if err.Error() == "监控不存在" {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		writeErr(w, http.StatusInternalServerError, "生成单监控年度 SLA 失败")
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, renderMonitorYearlySLAHTML(rep))
}

func (s *Server) handleMonitorYearlySLAPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "monitor_sla_year.html", "text/html; charset=utf-8")
}

func renderMonitorYearlySLAHTML(rep store.MonitorYearlySLAReport) string {
	var b strings.Builder

	name := html.EscapeString(rep.MonitorName)
	title := "单监控年度 SLA 报告 " + name + " " + fmt.Sprintf("%d", rep.Year)

	b.WriteString("<!DOCTYPE html>\n")
	b.WriteString("<html>\n")
	b.WriteString("<head><meta charset=\"utf-8\"><title>" + title + "</title></head>\n")
	b.WriteString("<body>\n")
	b.WriteString("<h1>" + title + "</h1>\n")
	b.WriteString("<p>全年聚合，目标 99.9%。</p>\n")

	yearStatus := "未达标"
	if rep.Met {
		yearStatus = "达标"
	}
	b.WriteString(fmt.Sprintf("<p>年度可用性：%.2f%%，检查总数：%d，最佳月份：%s，最差月份：%s，%s。</p>\n",
		rep.UptimePct, rep.TotalChecks, html.EscapeString(rep.BestMonth), html.EscapeString(rep.WorstMonth), yearStatus))

	b.WriteString("<table>\n")
	b.WriteString("<tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>达标</th></tr>\n")
	for _, it := range rep.Items {
		monthStatus := "未达标"
		if it.Met {
			monthStatus = "达标"
		}
		b.WriteString(fmt.Sprintf("<tr><td>%s</td><td>%.2f%%</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td></tr>\n",
			html.EscapeString(it.Month), it.UptimePct, it.TotalChecks, it.DownIncidents, slaDur(float64(it.TotalDowntimeSec)), monthStatus))
	}
	b.WriteString("</table>\n")

	b.WriteString("<h2>可用性条形</h2>\n")
	for _, it := range rep.Items {
		b.WriteString(fmt.Sprintf("<div style=\"width:%.2f%%\">%s %.2f%%</div>\n",
			it.UptimePct, html.EscapeString(it.Month), it.UptimePct))
	}

	b.WriteString("</body>\n</html>\n")
	return b.String()
}