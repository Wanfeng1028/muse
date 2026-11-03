package com.scaffold.admin;

import com.scaffold.common.exception.BusinessException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/test")
class TestExceptionController {

    @GetMapping("/business-error")
    void businessError() {
        throw new BusinessException("业务规则不允许该操作");
    }
}
