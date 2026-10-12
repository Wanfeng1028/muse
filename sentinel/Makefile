BINARY=sentinel

.PHONY: install build run dev test vet fmt clean

# 下载依赖
install:
	go mod download

# 构建可执行文件
build:
	go build -o $(BINARY) .

# 运行可执行文件
run:
	./$(BINARY)

# 开发模式运行
dev:
	go run .

# 运行测试
test:
	go test ./...

# 静态检查
vet:
	go vet ./...

# 格式化代码：先列出未格式化文件，再自动格式化
fmt:
	gofmt -l .
	gofmt -w .

# 清理构建产物与数据库文件
clean:
	rm -f $(BINARY)
	rm -rf data/*.db*
