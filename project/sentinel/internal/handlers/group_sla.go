package handlers

import (
	"fmt"
	"html"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"sentinel/internal/store"
)

func (s *Server) handleGroupSLAJSON(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
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
	report, err := s.store.GroupMonthlySLA(id, y, mo)
	if err != nil {
		if err.Error() == "分组不存在" {
			writeErr(w, http.StatusNotFound, "分组不存在")
		} else {
			writeErr(w, http.StatusInternalServerError, "生成分组 SLA 报告失败")
		}
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (s *Server) handleGroupSLAHTML(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的 id")
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
	rep, err := s.store.GroupMonthlySLA(id, y, mo)
	if err != nil {
		if err.Error() == "分组不存在" {
			writeErr(w, http.StatusNotFound, "分组不存在")
		} else {
			writeErr(w, http.StatusInternalServerError, "生成分组 SLA 报告失败")
		}
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(renderGroupSLAHTML(rep)))
}

func (s *Server) handleGroupSLAPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "group_sla.html", "text/html; charset=utf-8")
}

func renderGroupSLAHTML(rep store.GroupSLAReport) string {
	var b strings.Builder
	b.WriteString("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>分组 SLA 月报 " + html.EscapeString(rep.GroupName) + " " + rep.Month + "</title></head><body>")
	b.WriteString("<h1>分组 SLA 月报 " + html.EscapeString(rep.GroupName) + " " + rep.Month + "</h1>")
	b.WriteString("<div class=\"cards\">")
	b.WriteString("<div class=\"card\"><div class=\"label\">分组可用性</div><div class=\"value\">" + fmt.Sprintf("%.2f", rep.UptimePct) + "%</div></div>")
	b.WriteString("<div class=\"card\"><div class=\"label\">检查总数</div><div class=\"value\">" + fmt.Sprintf("%d", rep.TotalChecks) + "</div></div>")
	b.WriteString("<div class=\"card\"><div class=\"label\">宕机时长</div><div class=\"value\">" + slaDur(float64(rep.TotalDowntimeSec)) + "</div></div>")
	b.WriteString("<div class=\"card\"><div class=\"label\">事件总数</div><div class=\"value\">" + fmt.Sprintf("%d", rep.DownIncidents) + "</div></div>")
	b.WriteString("<div class=\"card\"><div class=\"label\">是否达标</div><div class=\"value\">")
	if rep.Met {
		b.WriteString("达标")
	} else {
		b.WriteString("未达标")
	}
	b.WriteString("</div></div>")
	b.WriteString("</div>")
	b.WriteString("<h2>组内监控</h2>")
	if len(rep.Monitors) == 0 {
		b.WriteString("<p>本组暂无监控</p>")
	} else {
		b.WriteString("<table><tr><th>监控</th><th>目标</th><th>可用性</th><th>检查数</th><th>事件数</th><th>宕机时长</th><th>达标</th></tr>")
		for _, m := range rep.Monitors {
			status := "未达标"
			if m.Met {
				status = "达标"
			}
			fmt.Fprintf(&b, "<tr><td>%s</td><td>%s</td><td>%.2f%%</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td></tr>", html.EscapeString(m.Name), html.EscapeString(m.Target), m.UptimePct, m.TotalChecks, m.DownIncidents, slaDur(float64(m.TotalDowntimeSec)), status)
		}
		b.WriteString("</table>")
	}
	b.WriteString("<h2>故障归因</h2>")
	if rep.DownIncidents == 0 {
		b.WriteString("<p>本月无故障事件</p>")
	} else {
		b.WriteString("<ul>")
		keys := make([]string, 0, len(rep.AttributionPct))
		for k := range rep.AttributionPct {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			fmt.Fprintf(&b, "<li>%s %.1f%%</li>", attribName(k), rep.AttributionPct[k])
		}
		b.WriteString("</ul>")
	}
	b.WriteString("</body></html>")
	return b.String()
}
