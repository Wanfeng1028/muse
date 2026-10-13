.PHONY: build run test vet fmt tidy clean

# 编译生成可执行文件到 bin/mortisedb
build:
	go build -o bin/mortisedb ./cmd/mortisedb

# 直接运行服务子命令
run:
	go run ./cmd/mortisedb serve

# 运行全部测试
test:
	go test ./...

# 静态检查
vet:
	go vet ./...

# 列出未格式化的文件
fmt:
	gofmt -l .

# 整理依赖
tidy:
	go mod tidy

# 清理构建产物与数据库文件
clean:
	rm -rf bin data/*.db*
