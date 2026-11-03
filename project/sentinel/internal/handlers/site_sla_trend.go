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

func parseSiteSLATrendParams(r *http.Request) (endYear, endMonth, months int, errMsg string) {
	end := r.URL.Query().Get("end")
	if end == "" {
		end = time.Now().UTC().Format("2006-01")
	}
	if len(end) != 7 || end[4] != '-' {
		return 0, 0, 0, "month 格式应为 YYYY-MM"
	}
	year, err := strconv.Atoi(end[:4])
	if err != nil {
		return 0, 0, 0, "month 格式应为 YYYY-MM"
	}
	month, err := strconv.Atoi(end[5:])
	if err != nil || year < 1970 || year > 9999 || month < 1 || month > 12 {
		return 0, 0, 0, "month 格式应为 YYYY-MM"
	}
	months = 6
	if monthsStr := r.URL.Query().Get("months"); monthsStr != "" {
		m, err := strconv.Atoi(monthsStr)
		if err != nil || m < 1 || m > 12 {
			return 0, 0, 0, "months 参数非法，取值 1~12"
		}
		months = m
	}
	return year, month, months, ""
}

func (s *Server) handleSiteSLATrendJSON(w http.ResponseWriter, r *http.Request) {
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	report, err := s.store.SiteSLATrend(endYear, endMonth, months)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站 SLA 趋势失败")
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func renderSiteSLATrendHTML(rep store.SiteSLATrendReport) string {
	var b strings.Builder
	b.WriteString("<!DOCTYPE html>\n")
	b.WriteString("<html lang=\"zh-CN\">\n")
	b.WriteString("<head>\n<meta charset=\"utf-8\">\n")
	b.WriteString("<title>全站 SLA 趋势 " + rep.EndMonth + "</title>\n")
	b.WriteString(`<style>
.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 4px;
}
.bar-month {
  width: 80px;
}
.bar-outer {
  flex: 1;
  background: #e5e7eb;
  height: 12px;
}
.bar-inner {
  background: #10b981;
  height: 12px;
}
.bar-text {
  width: 70px;
  text-align: right;
}
.trend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  margin-bottom: 4px;
}
.trend-month {
  width: 80px;
}
.trend-bar {
  flex: 1;
  background: #e5e7eb;
  height: 12px;
}
.trend-fill {
  background: #10b981;
  height: 12px;
}
.trend-pct {
  width: 70px;
  text-align: right;
}
</style>`)
	b.WriteString("</head>\n")
	b.WriteString("<body>\n")
	b.WriteString("<h1>全站 SLA 趋势 " + rep.EndMonth + "</h1>\n")
	b.WriteString(fmt.Sprintf("<p>最近 %d 个月全站聚合，目标 99.9%%。</p>\n", rep.Months))
	b.WriteString("<h2>逐月</h2>\n")
	b.WriteString("<table border=\"1\">\n")
	b.WriteString("<tr><th>月份</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>监控数</th><th>最差监控</th><th>达标</th></tr>\n")
	for _, it := range rep.Items {
		met := "未达标"
		if it.Met {
			met = "达标"
		}
		b.WriteString("<tr>")
		b.WriteString("<td>" + it.Month + "</td>")
		b.WriteString(fmt.Sprintf("<td>%.2f%%</td>", it.UptimePct))
		b.WriteString(fmt.Sprintf("<td>%d</td>", it.TotalChecks))
		b.WriteString(fmt.Sprintf("<td>%d</td>", it.DownIncidents))
		b.WriteString("<td>" + slaDur(float64(it.TotalDowntimeSec)) + "</td>")
		b.WriteString(fmt.Sprintf("<td>%d</td>", it.MonitorCount))
		b.WriteString("<td>" + html.EscapeString(it.WorstMonitorName) + "</td>")
		b.WriteString("<td>" + met + "</td>")
		b.WriteString("</tr>\n")
	}
	b.WriteString("</table>")

	b.WriteString("<h2>可用性条形</h2>\n")
	if len(rep.Items) == 0 {
		b.WriteString("<p>暂无数据</p>\n")
	} else {
		for _, m := range rep.Items {
			pct := fmt.Sprintf("%.2f", m.UptimePct)
			b.WriteString("<div class=\"trend-row\">")
			b.WriteString("<span class=\"trend-month\">" + m.Month + "</span>")
			b.WriteString("<div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:" + pct + "%\"></div></div>")
			b.WriteString("<span class=\"trend-pct\">" + pct + "%</span>")
			b.WriteString("</div>\n")
		}
	}
	b.WriteString("</body></html>\n")
	return b.String()
}

func (s *Server) handleSiteSLATrendHTML(w http.ResponseWriter, r *http.Request) {
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}
	rep, err := s.store.SiteSLATrend(endYear, endMonth, months)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站 SLA 趋势失败")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderSiteSLATrendHTML(rep)))
}

func (s *Server) handleSiteSLATrendPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "sla_trend.html", "text/html; charset=utf-8")
}
