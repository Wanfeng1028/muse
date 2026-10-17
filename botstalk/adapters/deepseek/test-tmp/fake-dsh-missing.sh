#!/bin/sh
echo '{"type":"session","sessionId":"fake-session"}'
echo "MISSING_CREDENTIAL: no api key" 1>&2
exit 0
