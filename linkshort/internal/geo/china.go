// internal/geo/china.go：内置中国省域 IP 段表，按 CIDR 最长前缀匹配。
//
// 数据来源：公开资料经 Keenable 搜索交叉核验（核验日期 2026-10-17），包括各公共 DNS 官方文档与第三方汇总。仅收录可交叉验证的知名段。
// 更新方式：本表为抽样非全量。增补时需用 Keenable 搜索该网段归属并交叉验证至少两个独立来源，核验通过后追加条目并更新核验日期。生产环境如需精确到省的全量解析，请配置 LINKSHORT_GEO_MMDB 使用完整 GeoIP2-City 数据库。
// 精度边界：1）anycast 段（如阿里/腾讯/百度 DNS）省份标注为运营商总部所在地，仅供粗略参考，不代表访问者实际省份；2）未收录的公网 IP 诚实返回 unknown，不猜测；3）内网/回环地址由责任链上游判为"内网"，不经过本表。
package geo

import (
	"log"
	"net"
	"strings"
)

// chinaRanges 为内置抽样 IP 段表；追加条目时必须同步更新文件头核验日期。
var chinaRanges = []struct {
	cidr, cc, country, province string
}{
	{"114.114.114.0/24", "CN", "中国", "江苏"},
	{"114.114.115.0/24", "CN", "中国", "江苏"},
	{"223.5.5.0/24", "CN", "中国", "浙江"},
	{"223.6.6.0/24", "CN", "中国", "浙江"},
	{"119.29.29.0/24", "CN", "中国", "广东"},
	{"182.254.116.0/24", "CN", "中国", "广东"},
	{"180.76.76.0/24", "CN", "中国", "北京"},
	{"1.2.4.0/24", "CN", "中国", "北京"},
	{"210.2.4.0/24", "CN", "中国", "北京"},
	{"2400:3200::/32", "CN", "中国", "浙江"},
	{"8.8.8.0/24", "US", "美国", "unknown"},
	{"8.8.4.0/24", "US", "美国", "unknown"},
	{"1.1.1.0/24", "US", "美国", "unknown"},
}

type chinaRange struct {
	network  *net.IPNet
	ones     int
	cc       string
	country  string
	province string
}

type cidrResolver struct {
	nets []chinaRange
}

func init() {
	var nets []chinaRange
	for _, item := range chinaRanges {
		_, network, err := net.ParseCIDR(item.cidr)
		if err != nil {
			log.Printf("geo: 跳过无效 CIDR %s: %v", item.cidr, err)
			continue
		}
		ones, _ := network.Mask.Size()
		nets = append(nets, chinaRange{
			network:  network,
			ones:     ones,
			cc:       item.cc,
			country:  item.country,
			province: item.province,
		})
	}
	builtinStatic = &cidrResolver{nets}
}

func (r *cidrResolver) Lookup(ip string) Location {
	if r == nil {
		return Unknown
	}

	addr := strings.TrimSpace(ip)
	if addr == "" {
		return Unknown
	}

	parsed := net.ParseIP(addr)
	if parsed == nil {
		return Unknown
	}

	var matched *chinaRange
	bestOnes := -1
	for i := range r.nets {
		item := &r.nets[i]
		if item.network == nil || !item.network.Contains(parsed) {
			continue
		}
		if item.ones > bestOnes {
			bestOnes = item.ones
			matched = item
		}
	}

	if matched == nil {
		return Unknown
	}

	return Location{
		CountryCode: matched.cc,
		CountryName: matched.country,
		Province:    matched.province,
		City:        Unknown.City,
	}
}
