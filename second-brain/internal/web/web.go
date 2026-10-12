package web

import (
	"embed"
	"io/fs"
)

//go:embed static/*
var FS embed.FS

// StaticFS returns the embedded static directory as an fs.FS.
func StaticFS() fs.FS {
	sub, err := fs.Sub(FS, "static")
	if err != nil {
		panic(err)
	}
	return sub
}
