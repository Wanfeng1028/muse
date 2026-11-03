#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo "some stderr" 1>&2
exit 2
