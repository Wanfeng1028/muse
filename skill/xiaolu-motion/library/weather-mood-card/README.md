# weather-mood-card · 时间天气心情卡 · Weather Mood Card

Small sticker-style cards — a clock-face time tag, a die-cut round weather sticker, a rounded mood ticket — pop onto the page with a springy scale-up.

## Source
`collage.py:time_card()` / `weather_card()` / `mood_card()`, dispatched via `vlog.py:card()`, demo `vlog_demo.mp4`, t=6.5-8.7s of the finished video (a time card and a mood card popping in together). Depends on the shared runtime in `../_shared/vlog-collage-runtime/` (see its README).

## How it works
Each card function in `collage.py` renders a self-contained sticker bitmap: `time_card()` composites a clock icon and "HH:MM" text onto a torn kraft tag with a strip of washi tape on top; `weather_card()` cuts a scalloped die-cut circle around a weather icon; `mood_card()` builds a rounded ticket with a face icon and a label. `vlog.py`'s `card(kind, key, at, t_end, x, y, rot, *args)` is the dispatcher that maps a `kind` string to the right builder, registers it, and wraps the result in an `El` (enter='pop' by default) so it scales in with a back-out overshoot at the given time and position.

## Notes
Face-free by inspection — this preview shows a cat and a hand holding a drink, no person on camera. `time_card()`/`weather_card()`/`mood_card()` are three of several small card builders in `collage.py`, which also holds the paper/tape/stamp primitives that `vlog.py`'s other element builders (`b_polaroid()`, `b_torn_print()`, etc.) draw on.
