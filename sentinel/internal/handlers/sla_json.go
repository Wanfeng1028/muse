package handlers

import (
	"fmt"
	"net/http"
	"strconv"
	"time"
)

// handleMonitorSLAJSON 月报 JSON；format=csv 时返回按日明细 CSV。
func (s *Server) handleMonitorSLAJSON(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
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
	if r.URL.Query().Get("format") == "csv" {
		days, err := s.store.DailySLA(id, y, mo)
		if err != nil {
			writeErr(w, http.StatusInternalServerError, "生成按日明细失败")
			return
		}
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		w.Header().Set("Content-Disposition", `attachment; filename="sla-`+month+`.csv"`)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte{0xEF, 0xBB, 0xBF})
		w.Write([]byte("date,uptime_pct,p95_latency_ms,total_checks,downtime_sec\n"))
		for _, p := range days {
			fmt.Fprintf(w, "%s,%.2f,%.2f,%d,%d\n", p.Date, p.UptimePct, p.P95LatencyMs, p.TotalChecks, p.DowntimeSec)
		}
		return
	}
	writeJSON(w, http.StatusOK, rep)
}
