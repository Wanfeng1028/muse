package store

import (
	"database/sql"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

// ErrNotFound 表示记录不存在。
var ErrNotFound = errors.New("record not found")

// timeLayout 是数据库里存储时间的统一格式（RFC3339 UTC）。
const timeLayout = time.RFC3339

// Store 封装 *sql.DB，提供业务层的读写方法。
type Store struct {
	db *sql.DB
}

// New 构造一个 Store。
func New(db *sql.DB) *Store {
	return &Store{db: db}
}

// Ping 检查数据库连通性。
func (s *Store) Ping() error {
	var one int
	if err := s.db.QueryRow("SELECT 1").Scan(&one); err != nil {
		return fmt.Errorf("ping db: %w", err)
	}
	return nil
}

// nowUTC 返回当前 UTC 时间，统一入口便于测试替换。
func nowUTC() time.Time { return time.Now().UTC() }

// formatTime 将 time.Time 转为存储字符串；nil 转为 NULL。
func formatTime(t time.Time) string {
	return t.UTC().Format(timeLayout)
}

// parseTime 解析存储的时间字符串。
func parseTime(s string) (time.Time, error) {
	return time.Parse(timeLayout, s)
}

// parseNullableTime 解析可能为空的时间字符串。
func parseNullableTime(ns sql.NullString) (*time.Time, error) {
	if !ns.Valid || ns.String == "" {
		return nil, nil
	}
	t, err := parseTime(ns.String)
	if err != nil {
		return nil, err
	}
	return &t, nil
}

// scanLink 从一行结果读取 Link。
func scanLink(scanner interface {
	Scan(dest ...any) error
}) (*model.Link, error) {
	var (
		l              model.Link
		enabled        int64
		expiresAt      sql.NullString
		maxVisits      sql.NullInt64
		burn           int64
		pwHash         sql.NullString
		purgeAfterBurn int64

		createdAt string
		updatedAt string
		burnedAt  sql.NullString
	)
	if err := scanner.Scan(
		&l.ID, &l.Slug, &l.URL, &l.Title, &l.Clicks,
		&enabled, &expiresAt, &maxVisits, &burn, &pwHash, &purgeAfterBurn, &createdAt, &updatedAt, &burnedAt,
	); err != nil {

		return nil, err
	}
	l.Enabled = enabled != 0
	ct, err := parseTime(createdAt)
	if err != nil {
		return nil, fmt.Errorf("parse created_at: %w", err)
	}
	l.CreatedAt = ct
	ut, err := parseTime(updatedAt)
	if err != nil {
		return nil, fmt.Errorf("parse updated_at: %w", err)
	}
	l.UpdatedAt = ut
	exp, err := parseNullableTime(expiresAt)
	if err != nil {
		return nil, fmt.Errorf("parse expires_at: %w", err)
	}
	l.ExpiresAt = exp
	if maxVisits.Valid {
		v := maxVisits.Int64
		l.MaxVisits = &v
	} else {
		l.MaxVisits = nil
	}
	l.Burn = burn != 0
	if pwHash.Valid {
		h := pwHash.String
		l.PasswordHash = &h
	} else {
		l.PasswordHash = nil
	}
	ba, err := parseNullableTime(burnedAt)
	if err != nil {
		return nil, fmt.Errorf("parse burned_at: %w", err)
	}
	l.BurnedAt = ba
	l.PurgeAfterBurn = purgeAfterBurn != 0
	return &l, nil
}

const linkColumns = `id, slug, url, title, clicks, enabled, expires_at, max_visits, burn, password_hash, purge_after_burn, created_at, updated_at, burned_at`

// CreateLink 创建短链。slug 为空时内部生成 6 位随机 slug，冲突时重试并加长。
// validURL 校验目标 URL：必须 http/https 开头且长度不超过 2048。
func validURL(u string) bool {
	if u == "" || len(u) > 2048 {
		return false
	}
	return strings.HasPrefix(u, "http://") || strings.HasPrefix(u, "https://")
}

func (s *Store) CreateLink(slug, url, title string, expiresAt *time.Time) (int64, error) {
	return s.CreateLinkEx(slug, url, title, expiresAt, nil, false, false)
}

// CreateLinkEx 与 CreateLink 逻辑一致，额外支持 maxVisits、burn 与 purge。
// maxVisits 为 nil 表示不限次数；burn 为 true 表示第一次成功跳转后自动禁用。
// purge 为 true 表示 burn 链接销毁后彻底删除行与访问日志（仅对 burn=1 有效）。
func (s *Store) CreateLinkEx(slug, url, title string, expiresAt *time.Time, maxVisits *int64, burn bool, purge bool) (int64, error) {

	if !validURL(url) {
		return 0, errors.New("url must start with http:// or https://")
	}
	now := nowUTC()
	nowStr := formatTime(now)
	var expStr sql.NullString
	if expiresAt != nil {
		expStr = sql.NullString{String: formatTime(*expiresAt), Valid: true}
	}
	var mv sql.NullInt64
	if maxVisits != nil {
		mv = sql.NullInt64{Int64: *maxVisits, Valid: true}
	}
	burnInt := int64(0)
	if burn {
		burnInt = 1
	}
	purgeInt := int64(0)
	if purge {
		purgeInt = 1
	}

	// 用户指定 slug 的分支。
	if slug != "" {
		if !util.IsValidSlug(slug) {
			return 0, util.ErrInvalidSlug
		}
		res, err := s.db.Exec(
			`INSERT INTO links (slug, url, title, clicks, enabled, expires_at, max_visits, burn, purge_after_burn, created_at, updated_at)
			 VALUES (?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?)`,
			slug, url, title, expStr, mv, burnInt, purgeInt, nowStr, nowStr,
		)

		if err != nil {
			return 0, fmt.Errorf("insert link: %w", err)
		}
		id, err := res.LastInsertId()
		if err != nil {
			return 0, fmt.Errorf("last insert id: %w", err)
		}
		return id, nil
	}

	// 自动生成 slug，冲突重试：前 5 次长度 6，之后逐步加长。
	const baseLen = 6
	const maxRetry = 5
	for attempt := 0; attempt <= maxRetry+5; attempt++ {
		length := baseLen
		if attempt > maxRetry {
			length = baseLen + (attempt - maxRetry)
		}
		if length > 64 {
			return 0, errors.New("slug generation failed: length limit reached")
		}
		generated, err := util.Generate(length)
		if err != nil {
			return 0, fmt.Errorf("generate slug: %w", err)
		}
		res, err := s.db.Exec(
			`INSERT INTO links (slug, url, title, clicks, enabled, expires_at, max_visits, burn, purge_after_burn, created_at, updated_at)
			 VALUES (?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?)`,
			generated, url, title, expStr, mv, burnInt, purgeInt, nowStr, nowStr,
		)

		if err == nil {
			id, lerr := res.LastInsertId()
			if lerr != nil {
				return 0, fmt.Errorf("last insert id: %w", lerr)
			}
			return id, nil
		}
		// 判断是否是 UNIQUE 冲突；若冲突则继续重试，否则直接返回。
		if !isUniqueConstraintErr(err) {
			return 0, fmt.Errorf("insert link: %w", err)
		}
	}
	return 0, errors.New("slug generation failed after retries")
}

// isUniqueConstraintErr 判断错误是否为唯一约束冲突。
func isUniqueConstraintErr(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "unique constraint") || strings.Contains(msg, "constraint failed")
}

// GetLink 根据 ID 查询短链。
func (s *Store) GetLink(id int64) (*model.Link, error) {
	row := s.db.QueryRow(`SELECT `+linkColumns+` FROM links WHERE id = ?`, id)
	l, err := scanLink(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return l, nil
}

// GetLinkBySlug 根据 slug 查询短链。
func (s *Store) GetLinkBySlug(slug string) (*model.Link, error) {
	row := s.db.QueryRow(`SELECT `+linkColumns+` FROM links WHERE slug = ?`, slug)
	l, err := scanLink(row)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return l, nil
}

// ListLinks 分页查询短链列表，并返回总数。
// orderBy 仅允许 "clicks" 或 "created_at"，其它值回落为 "created_at"。
// search 非空时匹配 slug/url/title（LIKE）。
func (s *Store) ListLinks(search string, page, perPage int, orderBy string) ([]*model.Link, int64, error) {
	return s.ListLinksFiltered(search, page, perPage, orderBy, nil)
}

func (s *Store) ListLinksFiltered(search string, page, perPage int, orderBy string, enabled *bool) ([]*model.Link, int64, error) {
	return s.ListLinksFilteredEx(search, page, perPage, orderBy, enabled, nil)
}

func (s *Store) ListLinksFilteredEx(search string, page, perPage int, orderBy string, enabled *bool, burn *bool) ([]*model.Link, int64, error) {
	return s.ListLinksFilteredEx2(search, page, perPage, orderBy, enabled, burn, nil)
}

func (s *Store) ListLinksFilteredEx2(search string, page, perPage int, orderBy string, enabled *bool, burn *bool, expired *bool) ([]*model.Link, int64, error) {
	return s.ListLinksFilteredEx3(search, page, perPage, orderBy, enabled, burn, expired, nil)
}

func (s *Store) ListLinksFilteredEx3(search string, page, perPage int, orderBy string, enabled *bool, burn *bool, expired *bool, hasPassword *bool) ([]*model.Link, int64, error) {
	if orderBy != "clicks" && orderBy != "created_at" {
		orderBy = "created_at"
	}
	if page < 1 {
		page = 1
	}
	if perPage < 1 {
		perPage = 20
	}
	if perPage > 200 {
		perPage = 200
	}

	var conds []string
	var args []any

	if search != "" {
		like := "%" + search + "%"
		conds = append(conds, "(slug LIKE ? OR url LIKE ? OR title LIKE ?)")
		args = append(args, like, like, like)
	}
	if enabled != nil {
		v := 0
		if *enabled {
			v = 1
		}
		conds = append(conds, "enabled = ?")
		args = append(args, v)
	}
	if burn != nil {
		v := 0
		if *burn {
			v = 1
		}
		conds = append(conds, "burn = ?")
		args = append(args, v)
	}
	if expired != nil {
		now := time.Now().UTC().Format(timeLayout)
		if *expired {
			conds = append(conds, "expires_at IS NOT NULL AND expires_at < ?")
		} else {
			conds = append(conds, "(expires_at IS NULL OR expires_at >= ?)")
		}
		args = append(args, now)
	}
	if hasPassword != nil {
		if *hasPassword {
			conds = append(conds, "password_hash IS NOT NULL AND password_hash != ''")
		} else {
			conds = append(conds, "(password_hash IS NULL OR password_hash = '')")
		}
	}

	cond := ""
	for i, c := range conds {
		if i == 0 {
			cond += " WHERE " + c
		} else {
			cond += " AND " + c
		}
	}

	var total int64
	countSQL := "SELECT COUNT(*) FROM links" + cond
	if err := s.db.QueryRow(countSQL, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count links: %w", err)
	}

	offset := (page - 1) * perPage
	listSQL := "SELECT " + linkColumns + " FROM links" + cond +
		" ORDER BY " + orderBy + " DESC, id DESC LIMIT ? OFFSET ?"
	listArgs := append(append([]any{}, args...), perPage, offset)

	rows, err := s.db.Query(listSQL, listArgs...)
	if err != nil {
		return nil, 0, fmt.Errorf("query links: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	var out []*model.Link
	for rows.Next() {
		l, err := scanLink(rows)
		if err != nil {
			return nil, 0, fmt.Errorf("scan link: %w", err)
		}
		out = append(out, l)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate links: %w", err)
	}
	return out, total, nil
}

// UpdateLink 更新短链的 title、enabled、expiresAt 字段。
func (s *Store) UpdateLink(id int64, title string, enabled bool, expiresAt *time.Time) error {
	return s.UpdateLinkEx(id, title, enabled, expiresAt, nil, false, false)
}

// UpdateLinkEx 更新短链的 title、enabled、expiresAt、maxVisits、burn、purge 字段。
// maxVisits 为 nil 表示不限次数；burn 为 true 表示阅后即焚。
// purge 为 true 表示 burn 链接销毁后彻底删除行与访问日志（仅对 burn=1 有效）。
func (s *Store) UpdateLinkEx(id int64, title string, enabled bool, expiresAt *time.Time, maxVisits *int64, burn bool, purge bool) error {

	var expStr sql.NullString
	if expiresAt != nil {
		expStr = sql.NullString{String: formatTime(*expiresAt), Valid: true}
	}
	en := int64(0)
	if enabled {
		en = 1
	}
	var mv sql.NullInt64
	if maxVisits != nil {
		mv = sql.NullInt64{Int64: *maxVisits, Valid: true}
	}
	burnInt := int64(0)
	if burn {
		burnInt = 1
	}
	purgeInt := int64(0)
	if purge {
		purgeInt = 1
	}
	res, err := s.db.Exec(
		`UPDATE links SET title = ?, enabled = ?, expires_at = ?, max_visits = ?, burn = ?, purge_after_burn = ?, updated_at = ? WHERE id = ?`,
		title, en, expStr, mv, burnInt, purgeInt, formatTime(nowUTC()), id,
	)

	if err != nil {
		return fmt.Errorf("update link: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// MarkBurned 将 burn=1 的链接置为 disabled（阅后即焚）。
// 目标不存在或 burn != 1 时返回 ErrNotFound。
func (s *Store) MarkBurned(id int64) error {
	res, err := s.db.Exec(
		`UPDATE links SET enabled = 0, burned_at = ?, updated_at = ? WHERE id = ? AND burn = 1`,
		formatTime(nowUTC()), formatTime(nowUTC()), id,
	)
	if err != nil {
		return fmt.Errorf("mark burned: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// PurgeExpiredBurned 删除销毁时间早于 before 的 burn 短链（burn=1 且 burned_at 已设置）。
// burned_at 为 NULL 的历史行（v1.5 之前销毁的）不在清理范围内，避免误删。
// 返回实际删除的行数；visits 通过外键 ON DELETE CASCADE 级联删除。
func (s *Store) PurgeExpiredBurned(before time.Time) (int64, error) {
	res, err := s.db.Exec(
		`DELETE FROM links WHERE burn = 1 AND burned_at IS NOT NULL AND burned_at < ?`,
		formatTime(before),
	)
	if err != nil {
		return 0, fmt.Errorf("purge expired burned: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("rows affected: %w", err)
	}
	return n, nil
}

// PurgeExpiredLinks 删除 expires_at 非 NULL 且早于 before 的链接（时间链清理）。
// burn 链由 PurgeExpiredBurned 按 burned_at 口径负责，本函数只看 expires_at；
// 两条扫荡先后执行，同一行不会被重复计数（DELETE 幂等）。
// expires_at 为 NULL（永不过期）的行不删。
// 返回实际删除的行数；visits 通过外键 ON DELETE CASCADE 级联删除。
func (s *Store) PurgeExpiredLinks(before time.Time) (int64, error) {
	res, err := s.db.Exec(
		`DELETE FROM links WHERE expires_at IS NOT NULL AND expires_at < ?`,
		formatTime(before),
	)
	if err != nil {
		return 0, fmt.Errorf("purge expired links: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("rows affected: %w", err)
	}
	return n, nil
}

// PurgeLink 彻底删除一条链接。visits 表的外键 ON DELETE CASCADE 会级联删除该链接的访问日志。
// 行不存在时返回 ErrNotFound。调用方负责只对 burn=1 且已销毁的链接调用。
func (s *Store) PurgeLink(id int64) error {
	res, err := s.db.Exec(`DELETE FROM links WHERE id = ?`, id)
	if err != nil {
		return fmt.Errorf("purge link: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// DeleteLink 删除短链，visits 通过外键 ON DELETE CASCADE 自动级联删除。
func (s *Store) DeleteLink(id int64) error {
	res, err := s.db.Exec(`DELETE FROM links WHERE id = ?`, id)
	if err != nil {
		return fmt.Errorf("delete link: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("rows affected: %w", err)
	}
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

// TryBurn 原子抢占 burn=1 链接的阅后即焚名额：
// 单条条件 UPDATE 将 enabled 由 1 置 0，只有第一个抢到的调用返回 true。
// 返回 false 表示"名额已被抢走，或链接非 burn/不存在"——调用方已在
// loadActiveLink 确认链接存在，故 false 一律视为该链已销毁。
func (s *Store) TryBurn(id int64) (bool, error) {
	res, err := s.db.Exec(
		`UPDATE links SET enabled = 0, burned_at = ?, updated_at = ? WHERE id = ? AND burn = 1 AND enabled = 1`,
		formatTime(nowUTC()), formatTime(nowUTC()), id,
	)
	if err != nil {
		return false, fmt.Errorf("try burn: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return false, fmt.Errorf("try burn rows: %w", err)
	}
	return n == 1, nil
}

// TryConsumeVisit 原子消费一次限次访问额度并同时计数：
// 单条条件 UPDATE 只在 clicks < max_visits（或 max_visits 为 NULL）时自增 clicks。
// 返回 true 表示已成功计数（额度已消费），false 表示额度用完。
// 调用方约定：返回 true 时需另行调用 RecordVisitNoCount 落 visits 行，
// 保证"每次 302 恰好对应 clicks+1 与一条 visits 记录"。
func (s *Store) TryConsumeVisit(id int64) (bool, error) {
	res, err := s.db.Exec(
		`UPDATE links SET clicks = clicks + 1 WHERE id = ? AND (max_visits IS NULL OR clicks < max_visits)`,
		id,
	)
	if err != nil {
		return false, fmt.Errorf("try consume visit: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return false, fmt.Errorf("try consume visit rows: %w", err)
	}
	return n == 1, nil
}

// insertVisitRow 在给定事务中插入一条 visits 记录（含地域四列），不触碰 clicks。
func insertVisitRow(tx *sql.Tx, linkID int64, ipHash, ua, referer, countryCode, countryName, province, city string) error {
	if _, err := tx.Exec(
		`INSERT INTO visits (link_id, ts, ip_hash, ua, referer, country_code, country_name, province, city) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		linkID, formatTime(nowUTC()), ipHash, ua, referer, countryCode, countryName, province, city,
	); err != nil {
		return fmt.Errorf("insert visit: %w", err)
	}
	return nil
}

// RecordVisit 在事务中插入 visits 并给 links.clicks 加 1。
// 老入口：地域记空=unknown。
func (s *Store) RecordVisit(linkID int64, ipHash, ua, referer string) error {
	return s.RecordVisitGeo(linkID, ipHash, ua, referer, "", "", "", "")
}

// RecordVisitGeo 在事务中插入 visits（含地域四列）并给 links.clicks 加 1。
func (s *Store) RecordVisitGeo(linkID int64, ipHash, ua, referer, countryCode, countryName, province, city string) error {
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	// 保证出错时回滚。
	defer func() {
		_ = tx.Rollback()
	}()

	if err := insertVisitRow(tx, linkID, ipHash, ua, referer, countryCode, countryName, province, city); err != nil {
		return err
	}
	if _, err := tx.Exec(`UPDATE links SET clicks = clicks + 1 WHERE id = ?`, linkID); err != nil {
		return fmt.Errorf("increment clicks: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}
	return nil
}

// RecordVisitNoCount 只插入一条 visits 记录（含地域四列），不修改 clicks。
// 供"已通过 TryConsumeVisit 完成计数"的路径使用，避免重复计数。
func (s *Store) RecordVisitNoCount(linkID int64, ipHash, ua, referer, countryCode, countryName, province, city string) error {
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	// 保证出错时回滚。
	defer func() {
		_ = tx.Rollback()
	}()

	if err := insertVisitRow(tx, linkID, ipHash, ua, referer, countryCode, countryName, province, city); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}
	return nil
}

// GeoStat 单条地域聚合统计。
type GeoStat struct {
	CountryCode string
	CountryName string
	Province    string
	City        string
	Clicks      int64
	UV          int64
}

// GeoOverview 地域分布聚合结果。
type GeoOverview struct {
	Items       []GeoStat
	TotalClicks int64
	TotalUV     int64
	UnknownPct  float64
	Days        int
}

// GeoStats 返回地域概览：按国家/省份/城市聚合的 TopN、总点击数、总 UV、unknown 占比。
// linkID>0 时只统计该短链；days>0 时只统计最近 days 天；country!="" 时只统计该国家。
// n<=0 时按 8 处理，n>100 时按 100 处理。
func (s *Store) GeoStats(linkID int64, days int, country string, n int) (GeoOverview, error) {
	if n <= 0 {
		n = 8
	}
	if n > 100 {
		n = 100
	}

	where := ""
	args := []any{}
	if linkID > 0 {
		where += " WHERE link_id = ?"
		args = append(args, linkID)
	}
	if days > 0 {
		cutoff := formatTime(nowUTC().AddDate(0, 0, -days))
		if where == "" {
			where = " WHERE ts >= ?"
		} else {
			where += " AND ts >= ?"
		}
		args = append(args, cutoff)
	}
	if country != "" {
		if where == "" {
			where = " WHERE country_code = ?"
		} else {
			where += " AND country_code = ?"
		}
		args = append(args, country)
	}

	var total int64
	if err := s.db.QueryRow("SELECT COUNT(*) FROM visits"+where, args...).Scan(&total); err != nil {
		return GeoOverview{}, fmt.Errorf("count visits: %w", err)
	}
	if total == 0 {
		return GeoOverview{Items: []GeoStat{}, Days: days}, nil
	}

	var totalUV int64
	if err := s.db.QueryRow(
		"SELECT COUNT(DISTINCT NULLIF(ip_hash,'')) FROM visits"+where, args...,
	).Scan(&totalUV); err != nil {
		return GeoOverview{}, fmt.Errorf("count uv: %w", err)
	}

	unknownCond := "country_code IN ('', 'unknown')"
	uWhere := " WHERE " + unknownCond
	if where != "" {
		uWhere = where + " AND " + unknownCond
	}
	var unknown int64
	if err := s.db.QueryRow("SELECT COUNT(*) FROM visits"+uWhere, args...).Scan(&unknown); err != nil {
		return GeoOverview{}, fmt.Errorf("count unknown visits: %w", err)
	}
	unknownPct := 100.0 * float64(unknown) / float64(total)

	knownCond := "country_code NOT IN ('', 'unknown')"
	kWhere := " WHERE " + knownCond
	if where != "" {
		kWhere = where + " AND " + knownCond
	}
	rows, err := s.db.Query(
		"SELECT country_code, country_name, province, city, COUNT(*) AS c, "+
			"COUNT(DISTINCT NULLIF(ip_hash,'')) AS uv FROM visits"+kWhere+
			" GROUP BY country_code, country_name, province, city ORDER BY c DESC LIMIT ?",
		append(args, n)...,
	)
	if err != nil {
		return GeoOverview{}, fmt.Errorf("query geo stats: %w", err)
	}
	defer rows.Close()
	items := make([]GeoStat, 0, n)
	for rows.Next() {
		var g GeoStat
		if err := rows.Scan(&g.CountryCode, &g.CountryName, &g.Province, &g.City, &g.Clicks, &g.UV); err != nil {
			return GeoOverview{}, fmt.Errorf("scan geo stats: %w", err)
		}
		items = append(items, g)
	}
	if err := rows.Err(); err != nil {
		return GeoOverview{}, fmt.Errorf("iterate geo stats: %w", err)
	}
	return GeoOverview{
		Items:       items,
		TotalClicks: total,
		TotalUV:     totalUV,
		UnknownPct:  unknownPct,
		Days:        days,
	}, nil
}

// HourlyStats 时段分布：24 小时点击分布（UTC 0-23）+ 星期分布（0=周日）。
// linkID>0 时只统计该短链；days>0 时只统计最近 days 天；days<=0 不限时间。
type HourlyStats struct {
	Hours    []int64 // 长度恒 24
	Weekdays []int64 // 长度恒 7，索引 0=周日（与 SQLite strftime('%w') 一致）
	Total    int64
	Days     int
	LinkID   int64
}

// HourlyStats 查询时段分布。
func (s *Store) HourlyStats(linkID int64, days int) (HourlyStats, error) {
	var st HourlyStats
	st.Hours = make([]int64, 24)
	st.Weekdays = make([]int64, 7)
	st.Days = days
	st.LinkID = linkID

	where := " WHERE 1=1"
	var args []any
	if linkID > 0 {
		where += " AND link_id = ?"
		args = append(args, linkID)
	}
	if days > 0 {
		cutoff := formatTime(nowUTC().AddDate(0, 0, -days))
		where += " AND ts >= ?"
		args = append(args, cutoff)
	}

	rows, err := s.db.Query("SELECT CAST(strftime('%H', ts) AS INTEGER) AS h, COUNT(*) FROM visits"+where+" GROUP BY h", args...)
	if err != nil {
		return st, fmt.Errorf("query hourly stats: %w", err)
	}
	for rows.Next() {
		var h int
		var c int64
		if err := rows.Scan(&h, &c); err != nil {
			rows.Close()
			return st, fmt.Errorf("scan hourly stats: %w", err)
		}
		if h >= 0 && h < 24 {
			st.Hours[h] = c
		}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return st, fmt.Errorf("iterate hourly stats: %w", err)
	}
	rows.Close()

	wrows, err := s.db.Query("SELECT CAST(strftime('%w', ts) AS INTEGER) AS w, COUNT(*) FROM visits"+where+" GROUP BY w", args...)
	if err != nil {
		return st, fmt.Errorf("query hourly stats: %w", err)
	}
	for wrows.Next() {
		var w int
		var c int64
		if err := wrows.Scan(&w, &c); err != nil {
			wrows.Close()
			return st, fmt.Errorf("scan hourly stats: %w", err)
		}
		if w >= 0 && w < 7 {
			st.Weekdays[w] = c
		}
	}
	if err := wrows.Err(); err != nil {
		wrows.Close()
		return st, fmt.Errorf("iterate hourly stats: %w", err)
	}
	wrows.Close()

	if err := s.db.QueryRow("SELECT COUNT(*) FROM visits"+where, args...).Scan(&st.Total); err != nil {
		return st, fmt.Errorf("count hourly stats: %w", err)
	}

	return st, nil
}

// uaClassifyDevice 按 UA 字符串判定设备类型，返回「手机 / 桌面 / 平板 / 爬虫 / 未知」之一。
// 判定顺序：先爬虫，再平板，再手机，再桌面，最后未知；匹配大小写不敏感。
func uaClassifyDevice(ua string) string {
	l := strings.ToLower(ua)
	if uaIsBot(l) {
		return "爬虫"
	}
	if strings.Contains(l, "ipad") || strings.Contains(l, "tablet") {
		return "平板"
	}
	if strings.Contains(l, "mobile") || strings.Contains(l, "android") ||
		strings.Contains(l, "iphone") || strings.Contains(l, "ipod") ||
		strings.Contains(l, "phone") {
		return "手机"
	}
	if strings.Contains(l, "windows") || strings.Contains(l, "macintosh") ||
		strings.Contains(l, "linux") || strings.Contains(l, "x11") ||
		strings.Contains(l, "desktop") {
		return "桌面"
	}
	return "未知"
}

// uaIsBot 判断 UA 是否命中爬虫特征词。入参必须为小写。
func uaIsBot(l string) bool {
	keywords := []string{
		"bot", "crawler", "spider", "slurp", "mediapartners",
		"wget", "curl", "python-requests", "scrapy",
	}
	for _, k := range keywords {
		if strings.Contains(l, k) {
			return true
		}
	}
	return false
}

// uaClassifyBrowser 按 UA 字符串判定浏览器，返回「Chrome / Edge / Firefox / Safari / 微信 / QQ / 其他」之一。
// 判定顺序：先微信与 QQ，再 Edge，再 Chrome，再 Firefox，最后 Safari 与其他；匹配大小写不敏感。
func uaClassifyBrowser(ua string) string {
	l := strings.ToLower(ua)
	if strings.Contains(l, "micromessenger") {
		return "微信"
	}
	if strings.Contains(l, "mqqbrowser") || strings.Contains(l, "qq/") {
		return "QQ"
	}
	if strings.Contains(l, "edg") {
		return "Edge"
	}
	if strings.Contains(l, "chrome") {
		return "Chrome"
	}
	if strings.Contains(l, "firefox") {
		return "Firefox"
	}
	if strings.Contains(l, "safari") {
		return "Safari"
	}
	return "其他"
}

// uaClassifyOS 按 UA 字符串判定操作系统，返回「Windows / macOS / Android / iOS / Linux / 其他」之一。
// 判定顺序：Android 先于 Linux，iOS 先于 macOS；匹配大小写不敏感。
func uaClassifyOS(ua string) string {
	l := strings.ToLower(ua)
	if strings.Contains(l, "windows") {
		return "Windows"
	}
	if strings.Contains(l, "android") {
		return "Android"
	}
	if strings.Contains(l, "iphone") || strings.Contains(l, "ipad") || strings.Contains(l, "ios") {
		return "iOS"
	}
	if strings.Contains(l, "macintosh") || strings.Contains(l, "mac os") {
		return "macOS"
	}
	if strings.Contains(l, "linux") || strings.Contains(l, "x11") {
		return "Linux"
	}
	return "其他"
}

// sortNamedStatsDesc 按 clicks 降序排序；clicks 相同时按名称升序，保证结果稳定。
func sortNamedStatsDesc(stats []model.NamedStat) {
	sort.SliceStable(stats, func(i, j int) bool {
		if stats[i].Clicks != stats[j].Clicks {
			return stats[i].Clicks > stats[j].Clicks
		}
		return stats[i].Name < stats[j].Name
	})
}

// UAStats 返回某个短链的 UA 画像聚合：设备 / 浏览器 / 操作系统分布与爬虫占比。
// SQL 只做 ua 分组计数，分类逻辑全部在 Go 侧完成。
func (s *Store) UAStats(linkID int64) (model.UAOverview, error) {
	var ov model.UAOverview
	ov.LinkID = linkID

	rows, err := s.db.Query(
		"SELECT ua, COUNT(*) AS c FROM visits WHERE link_id=? AND ua IS NOT NULL AND ua != '' GROUP BY ua ORDER BY c DESC",
		linkID,
	)
	if err != nil {
		return ov, fmt.Errorf("query ua stats: %w", err)
	}
	defer rows.Close()

	devices := make(map[string]int64)
	browsers := make(map[string]int64)
	osList := make(map[string]int64)

	for rows.Next() {
		var ua string
		var c int64
		if err := rows.Scan(&ua, &c); err != nil {
			return ov, fmt.Errorf("scan ua stats: %w", err)
		}
		device := uaClassifyDevice(ua)
		devices[device] += c
		if device == "爬虫" {
			ov.Bots += c
		}
		browsers[uaClassifyBrowser(ua)] += c
		osList[uaClassifyOS(ua)] += c
		ov.Total += c
	}
	if err := rows.Err(); err != nil {
		return ov, fmt.Errorf("iterate ua stats: %w", err)
	}

	ov.Devices = flattenNamedStats(devices)
	ov.Browsers = flattenNamedStats(browsers)
	ov.OSList = flattenNamedStats(osList)
	return ov, nil
}

// flattenNamedStats 把「名称 -> 点击量」映射展开为按 clicks 降序的切片。
func flattenNamedStats(m map[string]int64) []model.NamedStat {
	out := make([]model.NamedStat, 0, len(m))
	for name, clicks := range m {
		out = append(out, model.NamedStat{Name: name, Clicks: clicks})
	}
	sortNamedStatsDesc(out)
	return out
}

// StatsOverview 返回整体统计：总短链数、启用数、总点击数、今日点击数。

func (s *Store) StatsOverview() (links, enabledLinks, totalClicks, todayClicks int64, err error) {
	if err = s.db.QueryRow(`SELECT COUNT(*) FROM links`).Scan(&links); err != nil {
		return 0, 0, 0, 0, fmt.Errorf("count links: %w", err)
	}
	if err = s.db.QueryRow(`SELECT COUNT(*) FROM links WHERE enabled = 1`).Scan(&enabledLinks); err != nil {
		return 0, 0, 0, 0, fmt.Errorf("count enabled links: %w", err)
	}
	if err = s.db.QueryRow(`SELECT COALESCE(SUM(clicks), 0) FROM links`).Scan(&totalClicks); err != nil {
		return 0, 0, 0, 0, fmt.Errorf("sum clicks: %w", err)
	}
	// 今日 UTC 起点：now 截断到当天 00:00:00 UTC。
	now := nowUTC()
	dayStart := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	if err = s.db.QueryRow(
		`SELECT COUNT(*) FROM visits WHERE ts >= ? AND ts < ?`,
		formatTime(dayStart), formatTime(dayStart.Add(24*time.Hour)),
	).Scan(&todayClicks); err != nil {
		return 0, 0, 0, 0, fmt.Errorf("count today visits: %w", err)
	}
	return links, enabledLinks, totalClicks, todayClicks, nil
}

// dailyClicksQuery 是通用的按天聚合实现，把「从 ts >= 起」的 visits 按 UTC 日期分组，
// 并补齐缺失日期为 0。scope 参数为 SQL 片段（不含 WHERE 关键字），可能为 ""。
func (s *Store) dailyClicksQuery(days int, linkID *int64) ([]model.DailyStat, error) {
	if days < 1 {
		days = 1
	}
	if days > 3650 {
		days = 3650
	}
	now := nowUTC()
	dayStart := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	from := dayStart.AddDate(0, 0, -(days - 1))

	where := " WHERE ts >= ? AND ts < ?"
	args := []any{formatTime(from), formatTime(dayStart.Add(24 * time.Hour))}
	if linkID != nil {
		where += " AND link_id = ?"
		args = append(args, *linkID)
	}

	query := `SELECT substr(ts, 1, 10) AS d, COUNT(*) FROM visits` + where + ` GROUP BY d`
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("query daily clicks: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	// 把聚合结果放到 map，再按天补 0。
	byDay := make(map[string]int64, days)
	for rows.Next() {
		var d string
		var c int64
		if err := rows.Scan(&d, &c); err != nil {
			return nil, fmt.Errorf("scan daily click: %w", err)
		}
		byDay[d] = c
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate daily clicks: %w", err)
	}

	out := make([]model.DailyStat, 0, days)
	for i := 0; i < days; i++ {
		d := from.AddDate(0, 0, i).Format("2006-01-02")
		out = append(out, model.DailyStat{Date: d, Clicks: byDay[d]})
	}
	return out, nil
}

// DailyClicks 返回最近 days 天（含今天）的全站点击统计。
func (s *Store) DailyClicks(days int) ([]model.DailyStat, error) {
	return s.dailyClicksQuery(days, nil)
}

// LinkDailyClicks 返回指定短链最近 days 天（含今天）的点击统计。
func (s *Store) LinkDailyClicks(linkID int64, days int) ([]model.DailyStat, error) {
	return s.dailyClicksQuery(days, &linkID)
}

// TopLinks 返回点击量最高的 n 条短链（以 slug 作为 Name）。
func (s *Store) TopLinks(n int) ([]model.NamedStat, error) {
	if n < 1 {
		n = 1
	}
	if n > 1000 {
		n = 1000
	}
	rows, err := s.db.Query(
		`SELECT slug, clicks FROM links ORDER BY clicks DESC, id ASC LIMIT ?`, n,
	)
	if err != nil {
		return nil, fmt.Errorf("query top links: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	var out []model.NamedStat
	for rows.Next() {
		var st model.NamedStat
		if err := rows.Scan(&st.Name, &st.Clicks); err != nil {
			return nil, fmt.Errorf("scan top link: %w", err)
		}
		out = append(out, st)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate top links: %w", err)
	}
	return out, nil
}

// TopReferers 返回点击量最高的 n 个 referer（空 referer 用 "(direct)" 代替）。

func (s *Store) TopReferers(n int) ([]model.NamedStat, error) {
	if n < 1 {
		n = 1
	}
	if n > 1000 {
		n = 1000
	}
	rows, err := s.db.Query(
		`SELECT CASE WHEN referer = '' THEN '(direct)' ELSE referer END AS r,
		        COUNT(*) AS c
		 FROM visits
		 GROUP BY r
		 ORDER BY c DESC, r ASC
		 LIMIT ?`, n,
	)
	if err != nil {
		return nil, fmt.Errorf("query top referers: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	var out []model.NamedStat
	for rows.Next() {
		var st model.NamedStat
		if err := rows.Scan(&st.Name, &st.Clicks); err != nil {
			return nil, fmt.Errorf("scan top referer: %w", err)
		}
		out = append(out, st)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate top referers: %w", err)
	}
	return out, nil
}

// LinkTopReferers 统计指定链接的来源 Top N。
// 与 TopReferers 逻辑一致，只是通过 WHERE link_id = ? 限定到单条链接，
// 避免把全局统计误当成某条链的数据展示。空 referer 记为 (direct)。
func (s *Store) LinkTopReferers(linkID int64, n int) ([]model.NamedStat, error) {
	if n < 1 {
		n = 1
	}
	if n > 1000 {
		n = 1000
	}
	rows, err := s.db.Query(
		`SELECT CASE WHEN referer = '' THEN '(direct)' ELSE referer END AS r,
		        COUNT(*) AS c
		 FROM visits
		 WHERE link_id = ?
		 GROUP BY r
		 ORDER BY c DESC, r ASC
		 LIMIT ?`, linkID, n,
	)
	if err != nil {
		return nil, fmt.Errorf("query link top referers: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	var out []model.NamedStat
	for rows.Next() {
		var st model.NamedStat
		if err := rows.Scan(&st.Name, &st.Clicks); err != nil {
			return nil, fmt.Errorf("scan link top referer: %w", err)
		}
		out = append(out, st)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate link top referers: %w", err)
	}
	return out, nil
}

// ImportCSV 从 CSV 读取短链并批量导入。
// 列：slug,url,title,enabled,expires_at,max_visits,burn。
// 首行若为表头（slug,url,...）会自动跳过。返回成功数、跳过数、错误列表。
func (s *Store) ImportCSV(r io.Reader) (imported, skipped int, errs []string) {
	reader := csv.NewReader(r)
	reader.FieldsPerRecord = -1 // 允许列数不齐，由我们自行校验

	lineNo := 0
	for {
		rec, err := reader.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			errs = append(errs, fmt.Sprintf("line %d: read csv: %v", lineNo+1, err))
			// csv 读取出错时无法继续，直接返回。
			return imported, skipped, errs
		}
		lineNo++
		if len(rec) < 2 {
			errs = append(errs, fmt.Sprintf("line %d: expected at least 2 columns", lineNo))
			skipped++
			continue
		}
		// 跳过表头。
		if lineNo == 1 && strings.EqualFold(strings.TrimSpace(rec[0]), "slug") {
			continue
		}
		slug := strings.TrimSpace(rec[0])
		url := strings.TrimSpace(rec[1])
		title := ""
		if len(rec) > 2 {
			title = strings.TrimSpace(rec[2])
		}
		enabled := true
		if len(rec) > 3 && strings.TrimSpace(rec[3]) != "" {
			v, perr := strconv.ParseBool(strings.TrimSpace(rec[3]))
			if perr != nil {
				errs = append(errs, fmt.Sprintf("line %d: invalid enabled %q", lineNo, rec[3]))
				skipped++
				continue
			}
			enabled = v
		}
		var expiresAt *time.Time
		if len(rec) > 4 && strings.TrimSpace(rec[4]) != "" {
			t, perr := time.Parse(timeLayout, strings.TrimSpace(rec[4]))
			if perr != nil {
				errs = append(errs, fmt.Sprintf("line %d: invalid expires_at %q", lineNo, rec[4]))
				skipped++
				continue
			}
			expiresAt = &t
		}
		var maxVisits *int64
		if len(rec) > 5 && strings.TrimSpace(rec[5]) != "" {
			v, perr := strconv.ParseInt(strings.TrimSpace(rec[5]), 10, 64)
			if perr != nil || v < 1 || v > 1000000 {
				errs = append(errs, fmt.Sprintf("line %d: invalid max_visits %q", lineNo, rec[5]))
				skipped++
				continue
			}
			maxVisits = &v
		}
		burn := false
		if len(rec) > 6 && strings.TrimSpace(rec[6]) != "" {
			v, perr := strconv.ParseBool(strings.TrimSpace(rec[6]))
			if perr != nil {
				errs = append(errs, fmt.Sprintf("line %d: invalid burn %q", lineNo, rec[6]))
				skipped++
				continue
			}
			burn = v
		}
		// burn 与 max_visits 互斥：burn=true 时 max_visits 只能为空或 1。
		if burn && maxVisits != nil && *maxVisits != 1 {
			errs = append(errs, fmt.Sprintf("line %d: burn cannot combine with max_visits != 1", lineNo))
			skipped++
			continue
		}
		if url == "" {
			errs = append(errs, fmt.Sprintf("line %d: empty url", lineNo))
			skipped++
			continue
		}
		if slug != "" && !util.IsValidSlug(slug) {
			errs = append(errs, fmt.Sprintf("line %d: invalid slug %q", lineNo, slug))
			skipped++
			continue
		}

		id, cerr := s.CreateLinkEx(slug, url, title, expiresAt, maxVisits, burn, false)
		if cerr != nil {
			errs = append(errs, fmt.Sprintf("line %d: create link: %v", lineNo, cerr))
			skipped++
			continue
		}
		// 若导入数据里 enabled=false，则创建后再更新一次。
		if !enabled {
			if uerr := s.UpdateLinkEx(id, title, false, expiresAt, maxVisits, burn, false); uerr != nil {

				errs = append(errs, fmt.Sprintf("line %d: update enabled: %v", lineNo, uerr))
				skipped++
				continue
			}
		}
		imported++
	}
	return imported, skipped, errs
}

// ExportCSV 把所有短链按 slug,url,title,enabled,expires_at,max_visits,burn 导出到 w。
func (s *Store) ExportCSV(w io.Writer) error {
	rows, err := s.db.Query(`SELECT ` + linkColumns + ` FROM links ORDER BY id ASC`)
	if err != nil {
		return fmt.Errorf("query links for export: %w", err)
	}
	defer func() {
		_ = rows.Close()
	}()

	cw := csv.NewWriter(w)
	// 写表头。
	if err := cw.Write([]string{"slug", "url", "title", "enabled", "expires_at", "max_visits", "burn"}); err != nil {
		return fmt.Errorf("write header: %w", err)
	}
	for rows.Next() {
		l, err := scanLink(rows)
		if err != nil {
			return fmt.Errorf("scan link for export: %w", err)
		}
		enabledStr := "false"
		if l.Enabled {
			enabledStr = "true"
		}
		expiresStr := ""
		if l.ExpiresAt != nil {
			expiresStr = formatTime(*l.ExpiresAt)
		}
		maxVisitsStr := ""
		if l.MaxVisits != nil {
			maxVisitsStr = strconv.FormatInt(*l.MaxVisits, 10)
		}
		burnStr := "false"
		if l.Burn {
			burnStr = "true"
		}
		if err := cw.Write([]string{l.Slug, l.URL, l.Title, enabledStr, expiresStr, maxVisitsStr, burnStr}); err != nil {
			return fmt.Errorf("write row: %w", err)
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("iterate links for export: %w", err)
	}
	cw.Flush()
	if err := cw.Error(); err != nil {
		return fmt.Errorf("flush csv: %w", err)
	}
	return nil
}
