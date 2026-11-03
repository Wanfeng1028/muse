package web

import (
	"embed"
	"io/fs"
)

//go:embed webui/*
var embedded embed.FS

// StaticFS 返回内嵌的 webui 子目录文件系统。
func StaticFS() fs.FS {
	sub, err := fs.Sub(embedded, "webui")
	if err != nil {
		panic(err)
	}
	return sub
}
