GO ?= go
BIN := bin/linkshort

.PHONY: run build test vet fmt tidy docker clean backup restore drill


run:
	$(GO) run ./cmd/linkshort

build:
	@mkdir -p bin
	CGO_ENABLED=0 $(GO) build -trimpath -o $(BIN) ./cmd/linkshort

test:
	$(GO) test ./...

vet:
	$(GO) vet ./...

fmt:
	gofmt -w .

tidy:
	$(GO) mod tidy

docker:
	docker build -t linkshort:latest .

clean:
	rm -rf bin

backup:
	./scripts/backup.sh

restore:
	@if [ -z "$(BACKUP)" ]; then echo "用法: make restore BACKUP=backups/linkshort-YYYYmmdd-HHMMSS.db"; exit 2; fi
	./scripts/restore.sh $(BACKUP) --force

drill:
	./scripts/backup-drill.sh


