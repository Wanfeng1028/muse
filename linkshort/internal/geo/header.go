package geo

import (
	"os"
	"strings"
)

// HeaderNames 返回用于提取地域信息的请求头名称列表。
// 优先读取环境变量 LINKSHORT_GEO_HEADERS，按逗号分隔并去除空白；
// 环境变量为空时返回内置默认请求头列表。
func HeaderNames() []string {
	raw := os.Getenv("LINKSHORT_GEO_HEADERS")
	if strings.TrimSpace(raw) == "" {
		return []string{"X-Region", "X-Country-Code", "CF-IPCountry", "X-Client-Country"}
	}

	parts := strings.Split(raw, ",")
	names := make([]string, 0, len(parts))
	for _, part := range parts {
		name := strings.TrimSpace(part)
		if name == "" {
			continue
		}
		names = append(names, name)
	}
	return names
}

// countryNames 内置国家码到中文名称的映射表。
var countryNames = map[string]string{
	"CN": "中国",
	"HK": "中国香港",
	"TW": "中国台湾",
	"MO": "中国澳门",
	"US": "美国",
	"JP": "日本",
	"KR": "韩国",
	"SG": "新加坡",
	"GB": "英国",
	"DE": "德国",
	"FR": "法国",
	"AU": "澳大利亚",
	"CA": "加拿大",
	"RU": "俄罗斯",
	"IN": "印度",
	"BR": "巴西",
	"NL": "荷兰",
	"IE": "爱尔兰",
}

// isASCIILetter 判断字节是否为 ASCII 字母。
func isASCIILetter(b byte) bool {
	return (b >= 'A' && b <= 'Z') || (b >= 'a' && b <= 'z')
}

// LookupHeader 按给定顺序查找第一个非空请求头，并解析为 Location。
// get 为 nil 或所有请求头均为空时返回 Unknown。
func LookupHeader(get func(name string) string, names []string) Location {
	if get == nil {
		return Unknown
	}

	for _, name := range names {
		headerName := strings.TrimSpace(name)
		if headerName == "" {
			continue
		}

		value := strings.TrimSpace(get(headerName))
		if value == "" {
			continue
		}

		parts := strings.SplitN(value, ":", 2)
		country := strings.TrimSpace(parts[0])
		if len(country) != 2 {
			return Unknown
		}
		for i := 0; i < len(country); i++ {
			if !isASCIILetter(country[i]) {
				return Unknown
			}
		}

		code := strings.ToUpper(country)
		countryName, ok := countryNames[code]
		if !ok {
			countryName = code
		}

		province := Unknown.Province
		if len(parts) == 2 {
			if p := strings.TrimSpace(parts[1]); p != "" {
				province = p
			}
		}

		return Location{
			CountryCode: code,
			CountryName: countryName,
			Province:    province,
		}
	}

	return Unknown
}
