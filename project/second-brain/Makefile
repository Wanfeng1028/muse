# 声明伪目标，避免与同名文件冲突
.PHONY: build run test vet fmt tidy clean

# 编译服务端二进制到 bin/second-brain
build:
	go build -o bin/second-brain ./cmd/server

# 直接运行服务端
run:
	go run ./cmd/server

# 运行全部测试
test:
	go test ./...

# 静态检查
vet:
	go vet ./...

# 格式化代码
fmt:
	gofmt -w .

# 整理依赖
tidy:
	go mod tidy

# 清理构建产物与本地数据库
clean:
	rm -rf bin data/*.db
