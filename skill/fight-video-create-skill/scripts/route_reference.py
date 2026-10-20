#!/usr/bin/env python3
"""fight-video 资料库检索入口（封装形态）。

用法：
    python -X utf8 route_reference.py <scenes|design|moves|skills|scripts> --query "..."
    python -X utf8 route_reference.py --read <scope>/<id>

检索算法与资料正文都封装在 data/ 下的加密容器里，磁盘上没有任何可直接阅读的实现或正文。
载荷首字节标明类型：S = 混淆后的源码（与解释器版本无关），M = 编译后的字节码（按版本）。

本包支持的运行时：任意 Python 3.9+
"""
import marshal
import pathlib
import sys
from pathlib import Path as _rP

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import hashlib as _rh
import hmac as _rm
import lzma as _rl
import os as _ro

_R_MAGIC = b"FVB1"
_R_SN = 16384
_R_SR = 8
_R_SP = 1
_R_MEM = 64 * 1024 * 1024
_R_HEAD = 52


def _r_dk(_pw, _salt):
    return _rh.scrypt(
        _pw, salt=_salt, n=_R_SN, r=_R_SR, p=_R_SP, dklen=32, maxmem=_R_MEM
    )


def _r_ks(_key, _n, _nonce):
    _out = bytearray()
    _ctr = 0
    while len(_out) < _n:
        _out += _rm.new(
            _key, _nonce + _ctr.to_bytes(8, "big"), _rh.sha256
        ).digest()
        _ctr += 1
    return bytes(_out[:_n])


def _r_xor(_a, _b):
    """异或取 min(len) 字节。

    用大整数异或而不是 ``bytes(x ^ y for ...)``：后者是逐字节的 Python 循环，
    在 350 KB 正文上要烧掉约 0.3 s，占一次 --read 总耗时的近一半；前者是 C 速度，
    约 1 ms。``to_bytes`` 显式给长度，前导零字节不会丢。
    """
    _n = min(len(_a), len(_b))
    if _n == 0:
        return b""
    _x = int.from_bytes(_a[:_n], "big") ^ int.from_bytes(_b[:_n], "big")
    return _x.to_bytes(_n, "big")


def _r_seal(_pw, _plain):
    """明文 -> 加密容器。构建端使用。"""
    _body = _rl.compress(_plain, preset=6)
    _salt = _ro.urandom(16)
    _nonce = _ro.urandom(16)
    _key = _r_dk(_pw, _salt)
    _ct = _r_xor(_body, _r_ks(_key, len(_body), _nonce))
    _tag = _rm.new(_key, _R_MAGIC + _salt + _nonce + _ct, _rh.sha256).digest()[:16]
    return _R_MAGIC + _salt + _nonce + _tag + _ct


def _r_open(_pw, _raw):
    """加密容器 -> 明文。运行端使用；校验失败抛 ValueError。"""
    if _raw[:4] != _R_MAGIC:
        raise ValueError("bad container")
    _salt = _raw[4:20]
    _nonce = _raw[20:36]
    _tag = _raw[36:52]
    _ct = _raw[52:]
    if len(_ct) < 16 or _R_HEAD > len(_raw):
        raise ValueError("truncated container")
    _key = _r_dk(_pw, _salt)
    _want = _rm.new(_key, _raw[:36] + _ct, _rh.sha256).digest()[:16]
    if not _rm.compare_digest(_want, _tag):
        raise ValueError("bad key or corrupted payload")
    return _rl.decompress(_r_xor(_ct, _r_ks(_key, len(_ct), _nonce)))

_ROOT = _rP(__file__).resolve().parents[1]
_TAG = (getattr(sys.implementation, "cache_tag", "") or "").replace("-", "_")
_SUPPORTED = ["任意 Python 3.9+"]

_CANDIDATES = [_ROOT / "data" / "core.fvx"]
if _TAG:
    _CANDIDATES.insert(0, _ROOT / "data" / ("core." + _TAG + ".fvx"))
_PAYLOAD = next((p for p in _CANDIDATES if p.is_file()), None)

if _PAYLOAD is None:
    raise SystemExit(
        "本包不含当前 Python 的载荷：需要 %s，当前为 %s"
        % (", ".join(_SUPPORTED) or "(未知)", _TAG or "(未知)")
    )

_BLOB = _r_open(bytes.fromhex("4231bdadaaa68d093e160c3659454674"), _PAYLOAD.read_bytes())
_KIND = _BLOB[:1]
_NS = {"__name__": "_fvcore", "__file__": str(_ROOT / "scripts" / "_fvcore.py")}

if _KIND == b"S":
    exec(compile(_BLOB[1:].decode("utf-8"), "<fvcore>", "exec"), _NS)
elif _KIND == b"M":
    exec(marshal.loads(_BLOB[1:]), _NS)
else:
    raise SystemExit("载荷格式无法识别")

_FV = _NS["__fv__"]

_ARGV = sys.argv[1:]
if _ARGV and _ARGV[0] in ("--read", "-r", "read"):
    if len(_ARGV) < 2:
        raise SystemExit("用法: route_reference.py --read <scope>/<id>")
    raise SystemExit(_FV["read"](_ARGV[1]))

raise SystemExit(_FV["cli"](_ARGV))
