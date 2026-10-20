package store

import (
	"database/sql"
	"errors"
	"fmt"
	"math"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// DayStat 表示某一天的检查统计。
type DayStat struct {
	Date      string  `json:"date"`
	UptimePct float64 `json:"uptime_pct"`
	Checks    int     `json:"checks"`
	Failures  int     `json:"failures"`
}

// SLAReport 表示某个月的 SLA 报告。
type SLAReport struct {
	Month            string             `json:"month"`
	UptimePct        float64            `json:"uptime_pct"`
	TotalChecks      int                `json:"total_checks"`
	DownIncidents    int                `json:"down_incidents"`
	TotalDowntimeSec int64              `json:"total_downtime_sec"`
	Target           float64            `json:"sla_target"`
	Met              bool               `json:"met"`
	MTTRSec          float64            `json:"mttr_sec"`
	Severity         SeverityCounts     `json:"severity"`
	OpenIncidents    int                `json:"open_incidents"`
	Attribution      map[string]int     `json:"attribution"`
	AttributionPct   map[string]float64 `json:"attribution_pct"`
}

// SeverityCounts 表示按单次事件宕机时长分级的计数。
type SeverityCounts struct {
	P1 int `json:"p1"`
	P2 int `json:"p2"`
	P3 int `json:"p3"`
}

// classifySeverity 按单次事件宕机秒数分级：
// P1 严重 >= 1800 秒，P2 中等 >= 300 秒且 < 1800 秒，P3 轻微 < 300 秒。
func classifySeverity(secs int64) int {
	switch {
	case secs >= 1800:
		return 1
	case secs >= 300:
		return 2
	default:
		return 3
	}
}

// httpStatusRe 用于从 start_error 中提取 HTTP 状态码，匹配 实际 后跟 3 位数字。
var httpStatusRe = regexp.MustCompile(`实际\s*([0-9]{3})`)

// ClassifyFailureCause 对故障起始错误信息进行归因分类。
// 判定顺序（自上而下，命中即返回）：keyword > cert > dns > timeout > connection > http_5xx > other。
// 所有匹配均基于转小写后的子串匹配，http_5xx 额外使用正则提取状态码且要求 500<=code<=599（4xx 落 other）。
// 空字符串返回 other。
func ClassifyFailureCause(startError string) string {
	s := strings.ToLower(startError)
	if s == "" {
		return "other"
	}
	if strings.Contains(s, "关键字") || strings.Contains(s, "keyword") {
		return "keyword"
	}
	if strings.Contains(s, "证书") || strings.Contains(s, "certificate") || strings.Contains(s, "x509") || strings.Contains(s, "tls:") {
		return "cert"
	}
	if strings.Contains(s, "no such host") || strings.Contains(s, "dns") || strings.Contains(s, "域名解析") {
		return "dns"
	}
	if strings.Contains(s, "timeout") || strings.Contains(s, "deadline exceeded") || strings.Contains(s, "超时") {
		return "timeout"
	}
	if strings.Contains(s, "connection refused") || strings.Contains(s, "connection reset") || strings.Contains(s, "connect:") || strings.Contains(s, "network is unreachable") || strings.Contains(s, "no route to host") {
		return "connection"
	}
	if m := httpStatusRe.FindStringSubmatch(startError); m != nil {
		if code, err := strconv.Atoi(m[1]); err == nil && code >= 500 && code <= 599 {
			return "http_5xx"
		}
	}
	return "other"
}

// StatusPage 表示一个状态页。
type StatusPage struct {
	ID          int64  `json:"id"`
	TenantID    int64  `json:"tenant_id"`
	Slug        string `json:"slug"`
	Title       string `json:"title"`
	Theme       string `json:"theme"`
	AccentColor string `json:"accent_color"`
	CreatedAt   string `json:"created_at"`
}

// percentileLinear 使用线性插值法计算已排序切片的分位数。
// sorted 必须为升序；p 取值范围 [0,100]。空切片返回 0。
func percentileLinear(sorted []float64, p float64) float64 {
	n := len(sorted)
	if n == 0 {
		return 0
	}
	if n == 1 {
		return sorted[0]
	}
	if p <= 0 {
		return sorted[0]
	}
	if p >= 100 {
		return sorted[n-1]
	}
	// 使用 (n-1) 作为索引范围，符合常见分位数线性插值定义。
	rank := (p / 100.0) * float64(n-1)
	lo := int(rank)
	hi := lo + 1
	if hi >= n {
		return sorted[n-1]
	}
	frac := rank - float64(lo)
	return sorted[lo] + (sorted[hi]-sorted[lo])*frac
}

// LatencyPercentiles 返回指定天数内延迟的分位数 p50、p95、p99。
// 无数据时返回 0, 0, 0, nil。
func (s *Store) LatencyPercentiles(monitorID int64, days int) (p50, p95, p99 float64, err error) {
	if days <= 0 {
		days = 1
	}
	since := time.Now().AddDate(0, 0, -days).UTC().Format(time.RFC3339)
	rows, err := s.db.Query(
		`SELECT latency_ms FROM checks WHERE monitor_id = ? AND checked_at >= ? ORDER BY latency_ms ASC`,
		monitorID, since,
	)
	if err != nil {
		return 0, 0, 0, err
	}
	defer rows.Close()

	var vals []float64
	for rows.Next() {
		var v int64
		if err := rows.Scan(&v); err != nil {
			return 0, 0, 0, err
		}
		vals = append(vals, float64(v))
	}
	if err := rows.Err(); err != nil {
		return 0, 0, 0, err
	}
	if len(vals) == 0 {
		return 0, 0, 0, nil
	}
	sort.Float64s(vals)
	return percentileLinear(vals, 50), percentileLinear(vals, 95), percentileLinear(vals, 99), nil
}

// DailyBreakdown 返回最近 days 天每天按天分组的统计，按日期升序，包含无检查的天。
func (s *Store) DailyBreakdown(monitorID int64, days int) ([]DayStat, error) {
	if days <= 0 {
		days = 1
	}
	now := time.Now().UTC()
	// 计算起止日期（含今天共 days 天）。
	startDay := now.AddDate(0, 0, -(days - 1))
	startStr := startDay.Format("2006-01-02")

	rows, err := s.db.Query(
		`SELECT substr(checked_at,1,10) AS d, COUNT(*) AS total, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fails
		 FROM checks
		 WHERE monitor_id = ? AND substr(checked_at,1,10) >= ?
		 GROUP BY d`,
		monitorID, startStr,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	type agg struct {
		total int
		fails int
	}
	m := map[string]agg{}
	for rows.Next() {
		var d string
		var total, fails sql.NullInt64
		if err := rows.Scan(&d, &total, &fails); err != nil {
			return nil, err
		}
		m[d] = agg{total: int(total.Int64), fails: int(fails.Int64)}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	out := make([]DayStat, 0, days)
	for i := 0; i < days; i++ {
		day := startDay.AddDate(0, 0, i)
		key := day.Format("2006-01-02")
		ds := DayStat{Date: key, Checks: 0, Failures: 0, UptimePct: 100}
		if a, ok := m[key]; ok {
			ds.Checks = a.total
			ds.Failures = a.fails
			if a.total > 0 {
				ds.UptimePct = float64(a.total-a.fails) / float64(a.total) * 100.0
			} else {
				ds.UptimePct = 100
			}
		}
		out = append(out, ds)
	}
	return out, nil
}

// MonthlySLA 生成指定月份的 SLA 报告。
func (s *Store) MonthlySLA(monitorID int64, year, month int) (SLAReport, error) {
	report := SLAReport{
		Month:  fmt.Sprintf("%04d-%02d", year, month),
		Target: 99.9,
	}
	if month < 1 || month > 12 {
		return report, fmt.Errorf("非法月份: %d", month)
	}
	start := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	end := start.AddDate(0, 1, 0)
	startStr := start.Format(time.RFC3339)
	endStr := end.Format(time.RFC3339)

	// 检查总数与成功数。
	var total, okCount sql.NullInt64
	err := s.db.QueryRow(
		`SELECT COUNT(*), SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END)
		 FROM checks WHERE monitor_id = ? AND checked_at >= ? AND checked_at < ?`,
		monitorID, startStr, endStr,
	).Scan(&total, &okCount)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return report, err
	}
	report.TotalChecks = int(total.Int64)
	if report.TotalChecks > 0 {
		report.UptimePct = float64(okCount.Int64) / float64(report.TotalChecks) * 100.0
	} else {
		report.UptimePct = 100
	}

	// 区间内的 incidents。
	rows, err := s.db.Query(
		`SELECT started_at, ended_at, downtime_sec, start_error FROM incidents
		 WHERE monitor_id = ? AND started_at >= ? AND started_at < ?`,
		monitorID, startStr, endStr,
	)
	if err != nil {
		return report, err
	}
	defer rows.Close()

	now := time.Now().UTC()
	var sumDown int64
	var count int
	var closedCount int
	var closedSum int64
	var severity SeverityCounts
	var openCount int
	var attribution = map[string]int{}
	for rows.Next() {
		var startedAt string
		var endedAt sql.NullString
		var downtime sql.NullInt64
		var startError string
		if err := rows.Scan(&startedAt, &endedAt, &downtime, &startError); err != nil {
			return report, err
		}
		count++
		cause := ClassifyFailureCause(startError)
		attribution[cause]++
		if downtime.Valid {
			sumDown += downtime.Int64
			closedCount++
			closedSum += downtime.Int64
			switch classifySeverity(downtime.Int64) {
			case 1:
				severity.P1++
			case 2:
				severity.P2++
			default:
				severity.P3++
			}
		} else {
			// 未关闭：按查询时刻估算并裁剪到月份窗口（min(now, 月末) - started_at），
			// 避免查询过去月份时把窗口外的持续时间也算进来；查当前月时 end > now，行为不变。
			// started_at 必在窗口内（SQL 已保证 started_at >= start），只需裁剪上界。
			openCount++
			if t, perr := time.Parse(time.RFC3339, startedAt); perr == nil {
				effEnd := now
				if effEnd.After(end) {
					effEnd = end
				}
				secs := int64(effEnd.Sub(t).Seconds())
				if secs > 0 {
					sumDown += secs
					switch classifySeverity(secs) {
					case 1:
						severity.P1++
					case 2:
						severity.P2++
					default:
						severity.P3++
					}
				} else {
					severity.P3++
				}
			}
		}
	}
	if err := rows.Err(); err != nil {
		return report, err
	}
	report.DownIncidents = count
	report.TotalDowntimeSec = sumDown
	if closedCount > 0 {
		report.MTTRSec = float64(closedSum) / float64(closedCount)
	}
	report.Severity = severity
	report.OpenIncidents = openCount
	report.Attribution = attribution
	attributionPct := map[string]float64{}
	if report.DownIncidents > 0 {
		for k, v := range attribution {
			attributionPct[k] = math.Round(float64(v)/float64(report.DownIncidents)*100*10) / 10
		}
	}
	report.AttributionPct = attributionPct
	report.Met = report.UptimePct >= report.Target
	return report, nil
}

// CreateStatusPage 创建状态页，返回新 ID。
func (s *Store) CreateStatusPage(tenantID int64, slug, title string) (int64, error) {
	res, err := s.db.Exec(
		`INSERT INTO status_pages(tenant_id, slug, title, theme, accent_color, created_at) VALUES(?,?,?,?,?,?)`,
		tenantID, slug, title, "light", "", time.Now().UTC().Format(time.RFC3339),
	)
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// ListStatusPages 返回某租户下所有状态页。
func (s *Store) ListStatusPages(tenantID int64) ([]StatusPage, error) {
	rows, err := s.db.Query(
		`SELECT id, tenant_id, slug, title, theme, accent_color, created_at FROM status_pages WHERE tenant_id = ? ORDER BY id ASC`,
		tenantID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []StatusPage
	for rows.Next() {
		var sp StatusPage
		if err := rows.Scan(&sp.ID, &sp.TenantID, &sp.Slug, &sp.Title, &sp.Theme, &sp.AccentColor, &sp.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, sp)
	}
	return out, rows.Err()
}

// GetStatusPage 按 ID 查询状态页。
func (s *Store) GetStatusPage(id int64) (StatusPage, error) {
	var sp StatusPage
	err := s.db.QueryRow(
		`SELECT id, tenant_id, slug, title, theme, accent_color, created_at FROM status_pages WHERE id = ?`, id,
	).Scan(&sp.ID, &sp.TenantID, &sp.Slug, &sp.Title, &sp.Theme, &sp.AccentColor, &sp.CreatedAt)
	if err != nil {
		return sp, err
	}
	return sp, nil
}

// GetStatusPageBySlug 按 slug 查询状态页。
func (s *Store) GetStatusPageBySlug(slug string) (StatusPage, error) {
	var sp StatusPage
	err := s.db.QueryRow(
		`SELECT id, tenant_id, slug, title, theme, accent_color, created_at FROM status_pages WHERE slug = ?`, slug,
	).Scan(&sp.ID, &sp.TenantID, &sp.Slug, &sp.Title, &sp.Theme, &sp.AccentColor, &sp.CreatedAt)
	if err != nil {
		return sp, err
	}
	return sp, nil
}

// DeleteStatusPage 删除状态页（关联表由外键级联删除）。
func (s *Store) DeleteStatusPage(id int64) error {
	_, err := s.db.Exec(`DELETE FROM status_pages WHERE id = ?`, id)
	return err
}

// AddMonitorToPage 将 monitor 加入状态页（幂等）。
func (s *Store) AddMonitorToPage(pageID, monitorID int64) error {
	_, err := s.db.Exec(
		`INSERT OR IGNORE INTO status_page_monitors(page_id, monitor_id) VALUES(?,?)`,
		pageID, monitorID,
	)
	return err
}

// RemoveMonitorFromPage 将 monitor 从状态页移除。
func (s *Store) RemoveMonitorFromPage(pageID, monitorID int64) error {
	_, err := s.db.Exec(
		`DELETE FROM status_page_monitors WHERE page_id = ? AND monitor_id = ?`,
		pageID, monitorID,
	)
	return err
}

// ListPageMonitors 返回状态页中关联的所有 monitor。
func (s *Store) ListPageMonitors(pageID int64) ([]Monitor, error) {
	rows, err := s.db.Query(
		`SELECT m.id, m.name, m.kind, m.target, m.method, m.expected_status, m.timeout_sec, m.interval_sec,
		        m.enabled, m.webhook_url, m.tenant_id, m.is_public, m.cert_warn_days, m.keyword, m.keyword_mode, m.created_at, m.updated_at
		 FROM monitors m
		 JOIN status_page_monitors spm ON spm.monitor_id = m.id
		 WHERE spm.page_id = ?
		 ORDER BY m.id ASC`,
		pageID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Monitor
	for rows.Next() {
		var m Monitor
		if err := rows.Scan(
			&m.ID, &m.Name, &m.Kind, &m.Target, &m.Method, &m.ExpectedStatus,
			&m.TimeoutSec, &m.IntervalSec, &m.Enabled, &m.WebhookURL,
			&m.TenantID, &m.IsPublic, &m.CertWarnDays, &m.Keyword, &m.KeywordMode,
			&m.CreatedAt, &m.UpdatedAt,
		); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// SetMonitorPublic 设置 monitor 的公开可见性。
func (s *Store) SetMonitorPublic(monitorID int64, isPublic int) error {
	if isPublic != 0 {
		isPublic = 1
	}
	_, err := s.db.Exec(
		`UPDATE monitors SET is_public = ?, updated_at = ? WHERE id = ?`,
		isPublic, time.Now().UTC().Format(time.RFC3339), monitorID,
	)
	return err
}

// ValidPageThemes 列出状态页允许的主题取值。
var ValidPageThemes = map[string]bool{"light": true, "dark": true}

// validAccentColor 校验自定义主色：空字符串合法（用默认主色），
// 否则必须为 #rrggbb 形式的 6 位十六进制颜色。
func validAccentColor(c string) bool {
	if c == "" {
		return true
	}
	if len(c) != 7 || c[0] != '#' {
		return false
	}
	for _, r := range c[1:] {
		if !(r >= '0' && r <= '9' || r >= 'a' && r <= 'f' || r >= 'A' && r <= 'F') {
			return false
		}
	}
	return true
}

// UpdateStatusPageTheme 更新状态页主题与自定义主色。
// theme 必须为 light/dark；accentColor 为空或 #rrggbb；非法返回中文 error。
// 页面不存在返回 sql.ErrNoRows。
func (s *Store) UpdateStatusPageTheme(id int64, theme, accentColor string) error {
	if !ValidPageThemes[theme] {
		return errors.New("主题非法：仅支持 light/dark")
	}
	if !validAccentColor(accentColor) {
		return errors.New("主色非法：须为 #rrggbb 格式或空")
	}
	res, err := s.db.Exec(
		`UPDATE status_pages SET theme = ?, accent_color = ? WHERE id = ?`,
		theme, accentColor, id,
	)
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// 确保 strings 被使用（用于潜在的扩展）。
var _ = strings.TrimSpace
