"""单用户密码门核心逻辑。默认关闭；仅当配置含非空 password_hash 时开启；密码本身绝不存明文，配置里只放 werkzeug 哈希。"""

from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, current_app, make_response, redirect, render_template, request, session
from werkzeug.security import check_password_hash

SESSION_KEY = "feedflow_authed"


def is_auth_enabled(cfg: dict) -> bool:
    """判断密码门是否开启：配置中 auth_password_hash 为非空字符串时为真。"""
    if cfg is None:
        return False
    return isinstance(cfg.get("auth_password_hash"), str) and cfg["auth_password_hash"] != ""


def verify_password(cfg: dict, password: str) -> bool:
    """校验密码：未开启或密码非法返回假；哈希格式异常也返回假而不抛错。"""
    if not is_auth_enabled(cfg):
        return False
    if not isinstance(password, str) or password == "":
        return False
    try:
        return check_password_hash(cfg["auth_password_hash"], password)
    except Exception:  # noqa: BLE001  # 哈希格式非法也只算密码不对，不许把异常抛给调用方
        return False


def is_logged_in() -> bool:
    """判断当前会话是否已通过密码门。"""
    return session.get(SESSION_KEY) is True


def mark_logged_in() -> None:
    """标记当前会话已通过密码门，且不设为长期会话。"""
    session[SESSION_KEY] = True
    session.permanent = False


def mark_logged_out() -> None:
    """标记当前会话已登出。"""
    session.pop(SESSION_KEY, None)


auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login():
    """登录页：已登录则跳回 next；未开启密码门则跳回首页。"""
    cfg = current_app.config["FEEDFLOW"]
    if not is_auth_enabled(cfg):
        return redirect("/")
    if is_logged_in():
        return redirect(safe_next(request.args.get("next", "/")))
    return render_template(
        "login.html", error=None, next_value=safe_next(request.args.get("next", "/"))
    )


@auth_bp.post("/login")
def login_post():
    """提交密码：正确则建会话并跳回 next；错误则重渲表单并提示（未达锁定阈值时状态 200；锁定中或达到阈值时状态 429 并带 Retry-After）。"""
    cfg = current_app.config["FEEDFLOW"]
    if not is_auth_enabled(cfg):
        return redirect("/")
    next_value = safe_next(request.form.get("next", "/"))
    extensions = getattr(current_app, "extensions", None) or {}
    lockout = extensions.get("FEEDFLOW_LOGIN_LOCKOUT")
    key = request.remote_addr or "unknown"
    if lockout is not None and lockout.is_locked(key):
        resp = make_response(render_template("login.html", error="尝试次数过多，请稍后再试", next_value=next_value), 429)
        resp.headers["Retry-After"] = str(lockout.retry_after(key))
        return resp
    if verify_password(cfg, request.form.get("password", "")):
        if lockout is not None:
            lockout.record_success(key)
        mark_logged_in()
        return redirect(next_value)
    if lockout is not None:
        locked, _ = lockout.record_failure(key)
        if locked:
            resp = make_response(render_template("login.html", error="尝试次数过多，请稍后再试", next_value=next_value), 429)
            resp.headers["Retry-After"] = str(lockout.retry_after(key))
            return resp
    return render_template("login.html", error="密码不正确", next_value=next_value)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """登出：清会话后跳登录页。GET 亦可登出（单用户本机场景，登出 CSRF 影响仅限本人会话）。"""
    mark_logged_out()
    return redirect("/login")


def safe_next(value) -> str:
    """只允许以 / 开头且非 // 开头的相对路径，其余一律返回 /。"""
    if not isinstance(value, str) or not value.startswith("/"):
        return "/"
    if value.startswith(("//", "/\\")):
        return "/"
    parsed = urlparse(value)
    if parsed.netloc != "":
        return "/"
    return value
