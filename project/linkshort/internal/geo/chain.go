package geo

import (
	"log"
	"net"
	"os"
	"strings"
	"sync"
)

var (
	chainMu          sync.RWMutex
	chainMMDB        Resolver
	chainHeaderNames []string
)

// builtinStatic 内置地域表由 china.go 的 init() 注入；独立编译时保持全 unknown。
var builtinStatic Resolver = NewStatic(nil)

func init() {
	ReloadFromEnv()
}

// ReloadFromEnv 从环境变量重载请求地域解析配置。
// 使用 RWMutex 保护 chainMMDB/chainHeaderNames：测试期 ReloadFromEnv 与热路径 LookupRequest 可能并发。
func ReloadFromEnv() {
	names := HeaderNames()

	path := strings.TrimSpace(os.Getenv("LINKSHORT_GEO_MMDB"))
	if path == "" {
		path = strings.TrimSpace(os.Getenv("GEOIP_MMDB_PATH"))
	}

	var resolver Resolver
	if path != "" {
		db, err := Open(path)
		if err != nil {
			log.Printf("geo: 打开 mmdb 失败 (%s)：%v，mmdb 地域解析降级", path, err)
			resolver = nil
		} else {
			resolver = db
		}
	} else {
		log.Printf("geo: LINKSHORT_GEO_MMDB/GEOIP_MMDB_PATH 未配置，mmdb 地域解析降级")
		resolver = nil
	}

	chainMu.Lock()
	chainHeaderNames = names
	chainMMDB = resolver
	chainMu.Unlock()
}

func currentHeaderNames() []string {
	chainMu.RLock()
	defer chainMu.RUnlock()
	return chainHeaderNames
}

func currentMMDB() Resolver {
	chainMu.RLock()
	defer chainMu.RUnlock()
	return chainMMDB
}

// LookupRequest 按责任链解析 IP 地域：内网 → 云厂商头 → MMDB → 内置表 → unknown。
func LookupRequest(ip string, getHeader func(name string) string) Location {
	trimmed := strings.TrimSpace(ip)
	parsed := net.ParseIP(trimmed)
	if parsed == nil {
		return Unknown
	}

	if parsed.IsPrivate() || parsed.IsLoopback() || parsed.IsLinkLocalUnicast() || parsed.IsMulticast() || parsed.IsUnspecified() {
		return Location{CountryCode: "lan", CountryName: "内网", Province: "内网", City: "内网"}
	}

	if getHeader != nil {
		if loc := LookupHeader(getHeader, currentHeaderNames()); loc != Unknown {
			return loc
		}
	}

	if mmdb := currentMMDB(); mmdb != nil {
		if loc := mmdb.Lookup(trimmed); loc != Unknown {
			return loc
		}
	}

	if builtinStatic != nil {
		if loc := builtinStatic.Lookup(trimmed); loc != Unknown {
			return loc
		}
	}

	return Unknown
}

// requestResolver 是 FromEnv 兼容适配器。
type requestResolver struct{}

func (requestResolver) Lookup(ip string) Location {
	return LookupRequest(ip, nil)
}
