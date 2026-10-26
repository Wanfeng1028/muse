package handlers

import (
	"fmt"
	"html"
	"net/http"
	"strings"

	"sentinel/internal/store"
)

func (s *Server) handleSiteLatencyTrendJSON(w http.ResponseWriter, r *http.Request) {
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	report, err := s.store.SiteLatencyTrend(endYear, endMonth, months)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站延迟趋势失败")
		return
	}

	writeJSON(w, http.StatusOK, report)
}

func (s *Server) handleSiteLatencyTrendPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "latency_trend.html", "text/html; charset=utf-8")
}

func renderSiteLatencyTrendHTML(rep store.SiteLatencyTrendReport) string {
	var b strings.Builder

	b.WriteString(`<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>全站延迟趋势 `)
	b.WriteString(rep.EndMonth)
	b.WriteString(`</title>
<style>
body { font-family: sans-serif; margin: 24px; color: #1f2937; }
h1 { font-size: 20px; }
h2 { font-size: 16px; margin-top: 24px; }
table { border-collapse: collapse; margin-top: 8px; }
th, td { padding: 6px 10px; font-size: 13px; }
.trend-row { display: flex; align-items: center; margin: 4px 0; }
.trend-month { width: 80px; font-size: 12px; }
.trend-bar { width: 400px; height: 12px; background: #e5e7eb; }
.trend-fill { height: 12px; background: #2563eb; }
.trend-pct { width: 90px; text-align: right; font-size: 12px; margin-left: 8px; }
</style>
</head>
<body>
<h1>全站延迟趋势 `)
	b.WriteString(rep.EndMonth)
	fmt.Fprintf(&b, `</h1>
<p>最近 %d 个月全站成功检查延迟聚合，仅统计成功检查，失败检查不计入分位与均值。</p>
<h2>逐月</h2>
<table border="1">
<tr><th>月份</th><th>p50 (ms)</th><th>p95 (ms)</th><th>p99 (ms)</th><th>平均 (ms)</th><th>成功检查数</th><th>监控数</th><th>最慢监控</th></tr>
`, rep.Months)

	for _, it := range rep.Items {
		slowest := it.SlowestMonitorName
		if slowest == "" {
			slowest = "—"
		} else {
			slowest = html.EscapeString(slowest)
		}
		fmt.Fprintf(&b, "<tr><td>%s</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%d</td><td>%d</td><td>%s</td></tr>\n",
			it.Month, it.P50Ms, it.P95Ms, it.P99Ms, it.AvgMs, it.TotalChecks, it.MonitorCount, slowest)
	}

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
			pct := 0.0
			if maxP95 > 0 {
				pct = it.P95Ms / maxP95 * 100
			}
			fmt.Fprintf(&b, "<div class=\"trend-row\"><span class=\"trend-month\">%s</span><div class=\"trend-bar\"><div class=\"trend-fill\" style=\"width:%.2f%%\"></div></div><span class=\"trend-pct\">%.2f ms</span></div>\n",
				it.Month, pct, it.P95Ms)
		}
	}

	b.WriteString("</body>\n</html>\n")
	return b.String()
}

func (s *Server) handleSiteLatencyTrendHTML(w http.ResponseWriter, r *http.Request) {
	endYear, endMonth, months, errMsg := parseSiteSLATrendParams(r)
	if errMsg != "" {
		writeErr(w, http.StatusBadRequest, errMsg)
		return
	}

	rep, err := s.store.SiteLatencyTrend(endYear, endMonth, months)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成全站延迟趋势失败")
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderSiteLatencyTrendHTML(rep)))
}
