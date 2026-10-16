package geo

import (
	"net"
	"strings"

	"github.com/oschwald/geoip2-golang"
)

// Location 为一次 IP 解析结果。
type Location struct {
	CountryCode string // ISO 3166-1 alpha-2，如 "CN"；未知为 "unknown"
	CountryName string // 中文国名，如 "中国"；未知为 "unknown"
	Province    string // 中文省份，如 "广东"；未知为 "unknown"
	City        string // 中文城市，如"广州"；未知为 "unknown"
}

var Unknown = Location{CountryCode: "unknown", CountryName: "unknown", Province: "unknown", City: "unknown"}

type Resolver interface {
	// Lookup 解析 IP；任何失败/非法/内网 IP 返回 Unknown，绝不 panic。
	Lookup(ip string) Location
}

// normalizeIP 解析并校验字符串 IP；非法、内网、回环、组播、未指定、链路本地单播均返回 false。
func normalizeIP(s string) (net.IP, bool) {
	ip := net.ParseIP(strings.TrimSpace(s))
	if ip == nil {
		return nil, false
	}
	if ip.IsPrivate() || ip.IsLoopback() || ip.IsMulticast() || ip.IsUnspecified() || ip.IsLinkLocalUnicast() {
		return nil, false
	}
	return ip, true
}

// DB 为基于 mmdb 文件的 Resolver 实现。
type DB struct {
	reader *geoip2.Reader
}

// Open 打开 mmdb 文件；path 为空时返回错误。
func Open(path string) (*DB, error) {
	if path == "" {
		return nil, errEmptyPath
	}
	r, err := geoip2.Open(path)
	if err != nil {
		return nil, err
	}
	return &DB{reader: r}, nil
}

// Close 关闭底层 reader；reader 为 nil 时返回 nil。
func (d *DB) Close() error {
	if d == nil || d.reader == nil {
		return nil
	}
	return d.reader.Close()
}

// Lookup 解析 IP；任何失败/非法/内网 IP 返回 Unknown，绝不 panic。
func (d *DB) Lookup(ip string) Location {
	parsed, ok := normalizeIP(ip)
	if !ok {
		return Unknown
	}
	if d == nil || d.reader == nil {
		return Unknown
	}
	record, err := d.reader.City(parsed)
	if err != nil || record == nil {
		return Unknown
	}
	cc := record.Country.IsoCode
	if cc == "" {
		return Unknown
	}
	countryName := pickName(record.Country.Names, cc)
	province := Unknown.Province
	if len(record.Subdivisions) > 0 {
		sub := record.Subdivisions[0]
		province = pickName(sub.Names, sub.IsoCode)
	}
	city := pickName(record.City.Names, "")
	return Location{
		CountryCode: cc,
		CountryName: countryName,
		Province:    province,
		City:        city,
	}
}

// pickName 优先 zh-CN，其次 en，再次 fallback（可能为空）。
func pickName(names map[string]string, fallback string) string {
	if names != nil {
		if v := names["zh-CN"]; v != "" {
			return v
		}
		if v := names["en"]; v != "" {
			return v
		}
	}
	if fallback != "" {
		return fallback
	}
	return Unknown.CountryName
}

// staticResolver 基于内存映射的 Resolver。
type staticResolver struct {
	m map[string]Location
}

// NewStatic 返回基于静态表的 Resolver；查不到/非法 → Unknown。
func NewStatic(m map[string]Location) Resolver {
	return &staticResolver{m: m}
}

// Lookup 解析 IP；任何失败/非法/内网 IP 返回 Unknown，绝不 panic。
func (s *staticResolver) Lookup(ip string) Location {
	if s == nil || s.m == nil {
		return Unknown
	}
	if _, ok := normalizeIP(ip); !ok {
		return Unknown
	}
	key := strings.TrimSpace(ip)
	if loc, ok := s.m[key]; ok {
		return loc
	}
	return Unknown
}

// FromEnv 返回兼容旧签名的 Resolver，实际走 LookupRequest 完整责任链
// （内网 → 云厂商头 → MMDB → 内置表 → unknown）；不带请求头信息。
// 行为变化：未配置 mmdb 时不再全 unknown，内置表仍可命中。
func FromEnv() Resolver {
	return requestResolver{}
}
