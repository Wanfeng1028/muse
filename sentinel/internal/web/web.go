package web

import "embed"

// FS 内嵌 internal/web/static 目录下的全部静态资源，供 HTTP 服务直接读取。
//
//go:embed all:static
var FS embed.FS
