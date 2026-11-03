#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo '{"type":"status","phase":"turn_start","turn":1}'
echo '{"type":"status","phase":"step_start","turn":1}'
echo '{"type":"final","text":"fake-final-text"}'
exit 0
