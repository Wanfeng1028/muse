"""Base-clip camera: keyframed push-in / pan with easing, as ffmpeg expressions.

Keyframes (timeline seconds): {t, zoom>=1, cx, cy in 0..1, ease}; `ease` shapes the segment
that ENDS at that keyframe; before the first / after the last keyframe the value holds.
Zoom is interpolated in log space (constant perceived speed), centre linearly.

Window in the cover-fitted frame (W x H = canvas): w = W/z, h = H/z,
x = clamp(cx*W - w/2, 0, W - w), y = clamp(cy*H - h/2, 0, H - h).
The window always has the canvas aspect ratio, so the picture is scaled uniformly (never
stretched), and it never leaves the frame (no black edges).

Why `perspective` and not crop+scale: crop's output size is fixed at init and scale with
eval=frame changes the frame size mid-graph, so a crop/scale zoom snaps to whole pixels
(visible jitter on slow push-ins). `perspective=...:eval=frame` maps the window corners to
the output corners with sub-pixel (cubic) sampling, so the move is smooth. Expressions use
the filter's input frame counter `in`, which is 1 on the first frame: T = at + (in-1)/fps
(qa/camera_selftest.py caught the one-frame lead of the naive in/fps).
The same maths is implemented in Python (window(), to_canvas()) for QA and self-tests.
"""
import math

EASE_PY = {
    "lin": lambda x: x, "linear": lambda x: x, "step": lambda x: 1.0 if x >= 1 else 0.0,
    "sineIn": lambda x: 1 - math.cos(x * math.pi / 2), "sineOut": lambda x: math.sin(x * math.pi / 2),
    "sineInOut": lambda x: -(math.cos(math.pi * x) - 1) / 2,
    "quadIn": lambda x: x * x, "quadOut": lambda x: 1 - (1 - x) * (1 - x),
    "cubicIn": lambda x: x ** 3, "cubicOut": lambda x: 1 - (1 - x) ** 3,
    "cubicInOut": lambda x: 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2,
    "quintInOut": lambda x: 16 * x ** 5 if x < 0.5 else 1 - (-2 * x + 2) ** 5 / 2,
    "expoIn": lambda x: 0.0 if x <= 0 else (2 ** (10 * (x - 1)) - 2 ** -10) / (1 - 2 ** -10),
    "expoOut": lambda x: (1 - 2 ** (-10 * x)) / (1 - 2 ** -10),
    "expoInOut": lambda x: 0.0 if x <= 0 else 1.0 if x >= 1 else (2 ** (20 * x - 10) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2),
}
# same functions in ffmpeg expression syntax; X is the progress (0..1), stored in ld(0)
EASE_FF = {
    "lin": "X", "linear": "X", "step": "gte(X,1)",
    "sineIn": "(1-cos(X*PI/2))", "sineOut": "sin(X*PI/2)", "sineInOut": "(-(cos(PI*X)-1)/2)",
    "quadIn": "(X*X)", "quadOut": "(1-(1-X)*(1-X))", "cubicIn": "(X*X*X)", "cubicOut": "(1-pow(1-X,3))",
    "cubicInOut": "if(lt(X,0.5),4*X*X*X,1-pow(-2*X+2,3)/2)",
    "quintInOut": "if(lt(X,0.5),16*pow(X,5),1-pow(-2*X+2,5)/2)",
    "expoIn": "if(lte(X,0),0,(pow(2,10*(X-1))-pow(2,-10))/(1-pow(2,-10)))",
    "expoOut": "((1-pow(2,-10*X))/(1-pow(2,-10)))",
    "expoInOut": "if(lte(X,0),0,if(gte(X,1),1,if(lt(X,0.5),pow(2,20*X-10)/2,(2-pow(2,-20*X+10))/2)))",
}


def _clamp(v, a, b):
    return a if v < a else b if v > b else v


def state(keys, t):
    """-> (zoom, cx, cy) at timeline time t"""
    if t <= keys[0]["t"] or len(keys) == 1:
        k = keys[0]
        return k["zoom"], k["cx"], k["cy"]
    if t >= keys[-1]["t"]:
        k = keys[-1]
        return k["zoom"], k["cx"], k["cy"]
    for a, b in zip(keys, keys[1:]):
        if a["t"] <= t < b["t"]:
            x = _clamp((t - a["t"]) / max(1e-9, b["t"] - a["t"]), 0.0, 1.0)
            e = EASE_PY[b.get("ease", "sineInOut")](x)
            z = a["zoom"] * (b["zoom"] / a["zoom"]) ** e
            return z, a["cx"] + (b["cx"] - a["cx"]) * e, a["cy"] + (b["cy"] - a["cy"]) * e
    k = keys[-1]
    return k["zoom"], k["cx"], k["cy"]


def window(keys, t, W, H):
    z, cx, cy = state(keys, t)
    w, h = W / z, H / z
    return {"zoom": z, "x": _clamp(cx * W - w / 2, 0, W - w), "y": _clamp(cy * H - h / 2, 0, H - h), "w": w, "h": h}


def to_canvas(win, x, y):
    """point in the cover-fitted base frame -> canvas point"""
    return (x - win["x"]) * win["zoom"], (y - win["y"]) * win["zoom"]


def is_static(keys):
    return all(abs(k["zoom"] - keys[0]["zoom"]) < 1e-9 and abs(k["cx"] - keys[0]["cx"]) < 1e-9 and abs(k["cy"] - keys[0]["cy"]) < 1e-9 for k in keys)


def _f(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") if "." in f"{v:.6f}" else str(v)


def ff_value(keys, T, which):
    """ffmpeg expression for zoom / cx / cy at timeline time expression T"""
    def val(k):
        return k["zoom"] if which == "zoom" else k[which]
    if len(keys) == 1:
        return _f(val(keys[0]))
    expr = _f(val(keys[-1]))
    for a, b in reversed(list(zip(keys, keys[1:]))):
        d = max(1e-9, b["t"] - a["t"])
        X = f"clip(({T}-{_f(a['t'])})/{_f(d)},0,1)"
        e = EASE_FF[b.get("ease", "sineInOut")].replace("X", X)
        if which == "zoom":
            seg = f"{_f(val(a))}*pow({_f(val(b) / val(a))},{e})"
        else:
            seg = f"({_f(val(a))}+({_f(val(b) - val(a))})*{e})"
        expr = f"if(lt({T},{_f(b['t'])}),{seg},{expr})"
    return f"if(lt({T},{_f(keys[0]['t'])}),{_f(val(keys[0]))},{expr})"


def perspective_filter(keys, at, fps, W, H):
    """perspective filter string for a clip whose first frame sits at timeline time `at`"""
    T = f"({_f(at)}+(in-1)/{fps})"     # `in` is already 1 on the first frame (measured by qa/camera_selftest.py)
    Z = ff_value(keys, T, "zoom")
    CX, CY = ff_value(keys, T, "cx"), ff_value(keys, T, "cy")
    w, h = f"({W}/({Z}))", f"({H}/({Z}))"
    X = f"clip({CX}*{W}-{w}/2,0,{W}-{w})"
    Y = f"clip({CY}*{H}-{h}/2,0,{H}-{h})"
    x1, y2 = f"({X}+{w})", f"({Y}+{h})"
    esc = lambda s: s.replace(",", r"\,")
    return ("perspective=" + ":".join([f"x0='{esc(X)}'", f"y0='{esc(Y)}'", f"x1='{esc(x1)}'", f"y1='{esc(Y)}'",
                                       f"x2='{esc(X)}'", f"y2='{esc(y2)}'", f"x3='{esc(x1)}'", f"y3='{esc(y2)}'"])
            + ":interpolation=cubic:sense=source:eval=frame")
