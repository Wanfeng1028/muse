package com.scaffold.admin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.mybatis.spring.annotation.MapperScan;

@MapperScan({
        "com.scaffold.system.mapper",
        "com.scaffold.generator.mapper"
})
@SpringBootApplication(scanBasePackages = "com.scaffold")
public class ScaffoldAdminApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScaffoldAdminApplication.class, args);
    }
}
