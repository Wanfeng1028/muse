mkdir -p /backup/mortisedb/$(date +%F)
sqlite3 data/mortise.db ".backup '/backup/mortisedb/$(date +%F)/mortise.db'"
cp mortise.yaml /backup/mortisedb/$(date +%F)/mortise.yaml
