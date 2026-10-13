package com.dramafactory;

import com.dramafactory.config.EgressProxyConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DramaFactoryApplication {
    public static void main(String[] args) {
        // 先配置出口代理（若环境有 HTTPS_PROXY），再启动 Spring，确保所有 HttpClient 走代理
        EgressProxyConfig.configureFromEnv();
        SpringApplication.run(DramaFactoryApplication.class, args);
    }
}
