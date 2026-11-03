package api

import (
	"net/http"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// CurrentUser 从请求中解析当前用户身份（单机多用户简化方案）。
//
// 优先级：X-User 请求头 > ?user= 查询参数 > 默认 store.DefaultUser("local")。
// 无注册、无鉴权：同一台机器上的多个人靠自觉声明身份；前端侧边栏的用户
// 切换器把选择写入 localStorage 并随每个请求发送 X-User 头。
// 不传身份时行为与开放模式一致：全部数据归属 local。
func CurrentUser(r *http.Request) string {
	if u := r.Header.Get("X-User"); u != "" {
		return store.NormalizeUser(u)
	}
	if u := r.URL.Query().Get("user"); u != "" {
		return store.NormalizeUser(u)
	}
	return store.DefaultUser
}
