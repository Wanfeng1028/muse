GO ?= go
BIN := bin/linkshort

.PHONY: run build test vet fmt tidy docker clean

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
