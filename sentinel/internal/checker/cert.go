package checker

import (
	"crypto/tls"
	"fmt"
	"net"
	"net/url"
	"strings"
	"time"
)

// ParseTLSHostPort 从 https URL 解析出 host:port，默认 443。
// target 非 https 前缀返回中文错误。
func ParseTLSHostPort(target string) (string, error) {
	if !strings.HasPrefix(target, "https://") {
		return "", fmt.Errorf("目标非 https，无法进行证书检查: %s", target)
	}
	rest := strings.TrimPrefix(target, "https://")
	if i := strings.Index(rest, "/"); i >= 0 {
		rest = rest[:i]
	}
	if rest == "" {
		return "", fmt.Errorf("目标缺少主机名: %s", target)
	}
	u, err := url.Parse("https://" + rest)
	if err != nil {
		return "", fmt.Errorf("解析目标主机失败: %s: %w", target, err)
	}
	host := u.Hostname()
	if host == "" {
		return "", fmt.Errorf("目标缺少主机名: %s", target)
	}
	port := u.Port()
	if port == "" {
		port = "443"
	}
	return host + ":" + port, nil
}

// CheckCertExpiry 直连目标的 TLS 端口读取叶子证书剩余天数。
// 用 tls.Dial（InsecureSkipVerify=true，只读有效期不校验链），超时用 timeout。
// 返回剩余天数（向下取整天数，可为负表示已过期）、是否触发预警、错误。
// warn = warnDays > 0 && daysLeft < warnDays。
//
// 取舍理由：本函数只关心叶子证书的有效期，不参与信任链校验，
// 因此显式设置 InsecureSkipVerify=true，避免因中间证书缺失或
// 自签名证书导致握手失败而无法读取到期时间；信任链校验由其他环节负责。
func CheckCertExpiry(target string, warnDays int, timeout time.Duration) (daysLeft int, warn bool, err error) {
	addr, err := ParseTLSHostPort(target)
	if err != nil {
		return 0, false, err
	}
	dialer := &net.Dialer{Timeout: timeout}
	conn, err := tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{InsecureSkipVerify: true})
	if err != nil {
		return 0, false, fmt.Errorf("TLS 握手失败: %s: %w", addr, err)
	}
	defer conn.Close()

	certs := conn.ConnectionState().PeerCertificates
	if len(certs) == 0 {
		return 0, false, fmt.Errorf("对端未提供证书: %s", addr)
	}
	leaf := certs[0]
	daysLeft = int(time.Until(leaf.NotAfter).Hours() / 24)
	warn = warnDays > 0 && daysLeft < warnDays
	return daysLeft, warn, nil
}
