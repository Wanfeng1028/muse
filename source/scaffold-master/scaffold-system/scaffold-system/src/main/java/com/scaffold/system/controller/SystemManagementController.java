package com.scaffold.system.controller;

import com.scaffold.common.domain.PageQuery;
import com.scaffold.common.domain.PageResult;
import com.scaffold.common.domain.R;
import com.scaffold.framework.audit.OperLog;
import com.scaffold.framework.security.RequiresPermission;
import com.scaffold.system.domain.dto.ConfigWriteRequest;
import com.scaffold.system.domain.dto.DeptWriteRequest;
import com.scaffold.system.domain.dto.DictDataWriteRequest;
import com.scaffold.system.domain.dto.DictTypeWriteRequest;
import com.scaffold.system.domain.dto.MenuWriteRequest;
import com.scaffold.system.domain.dto.PostWriteRequest;
import com.scaffold.system.domain.dto.RoleWriteRequest;
import com.scaffold.system.domain.dto.UserPasswordResetRequest;
import com.scaffold.system.domain.dto.UserStatusRequest;
import com.scaffold.system.domain.dto.UserWriteRequest;
import com.scaffold.system.domain.vo.IdResponse;
import com.scaffold.system.service.SystemManagementService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/system")
public class SystemManagementController {

    private final SystemManagementService service;

    public SystemManagementController(SystemManagementService service) {
        this.service = service;
    }

    @GetMapping("/users")
    @RequiresPermission("system:user:list")
    public R<PageResult<Map<String, Object>>> users(
            PageQuery query,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) Long deptId,
            @RequestParam(required = false) Long postId
    ) {
        return R.success(service.users(query, keyword, status, deptId, postId));
    }

    @GetMapping("/users/options")
    @RequiresPermission("system:user:list")
    public R<Map<String, Object>> userOptions() {
        return R.success(service.userOptions());
    }

    @GetMapping("/users/export")
    @RequiresPermission("system:user:list")
    public ResponseEntity<String> exportUsers(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) Long deptId,
            @RequestParam(required = false) Long postId
    ) {
        return csv("users.csv", service.exportUsers(keyword, status, deptId, postId));
    }

    @PostMapping("/users")
    @RequiresPermission("system:user:add")
    @OperLog(module = "用户管理", action = "新增")
    public R<IdResponse> createUser(@RequestBody UserWriteRequest request) {
        return R.success(service.createUser(request));
    }

    @PutMapping("/users/{id}")
    @RequiresPermission("system:user:edit")
    @OperLog(module = "用户管理", action = "修改")
    public R<Void> updateUser(@PathVariable Long id, @RequestBody UserWriteRequest request) {
        service.updateUser(id, request);
        return R.success(null);
    }

    @PutMapping("/users/{id}/status")
    @RequiresPermission("system:user:edit")
    @OperLog(module = "用户管理", action = "状态变更")
    public R<Void> updateUserStatus(@PathVariable Long id, @RequestBody UserStatusRequest request) {
        service.updateUserStatus(id, request);
        return R.success(null);
    }

    @PutMapping("/users/{id}/password")
    @RequiresPermission("system:user:resetPwd")
    @OperLog(module = "用户管理", action = "重置密码")
    public R<Void> resetUserPassword(@PathVariable Long id, @RequestBody UserPasswordResetRequest request) {
        service.resetUserPassword(id, request);
        return R.success(null);
    }

    @DeleteMapping("/users/{id}")
    @RequiresPermission("system:user:remove")
    @OperLog(module = "用户管理", action = "删除")
    public R<Void> deleteUser(@PathVariable Long id) {
        service.deleteUser(id);
        return R.success(null);
    }

    private ResponseEntity<String> csv(String filename, String content) {
        return ResponseEntity.ok()
                .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .body(content);
    }

    @GetMapping("/roles/export")
    @RequiresPermission("system:role:list")
    public ResponseEntity<String> exportRoles(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return csv("roles.csv", service.exportRoles(keyword, status));
    }

    @GetMapping("/roles")
    @RequiresPermission("system:role:list")
    public R<PageResult<Map<String, Object>>> roles(
            PageQuery query,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return R.success(service.roles(query, keyword, status));
    }

    @GetMapping("/permissions/graph")
    @RequiresPermission("system:role:list")
    public R<Map<String, Object>> permissionGraph() {
        return R.success(service.permissionGraph());
    }

    @GetMapping("/roles/{id}/menus")
    @RequiresPermission("system:role:list")
    public R<Map<String, Object>> roleMenus(@PathVariable Long id) {
        return R.success(service.roleMenus(id));
    }

    @PostMapping("/roles")
    @RequiresPermission("system:role:add")
    @OperLog(module = "角色管理", action = "新增")
    public R<IdResponse> createRole(@RequestBody RoleWriteRequest request) {
        return R.success(service.createRole(request));
    }

    @PutMapping("/roles/{id}")
    @RequiresPermission("system:role:edit")
    @OperLog(module = "角色管理", action = "修改")
    public R<Void> updateRole(@PathVariable Long id, @RequestBody RoleWriteRequest request) {
        service.updateRole(id, request);
        return R.success(null);
    }

    @DeleteMapping("/roles/{id}")
    @RequiresPermission("system:role:remove")
    @OperLog(module = "角色管理", action = "删除")
    public R<Void> deleteRole(@PathVariable Long id) {
        service.deleteRole(id);
        return R.success(null);
    }

    @GetMapping("/menus/export")
    @RequiresPermission("system:menu:list")
    public ResponseEntity<String> exportMenus(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return csv("menus.csv", service.exportMenus(keyword, status));
    }

    @GetMapping("/menus/tree")
    @RequiresPermission("system:menu:list")
    public R<List<Map<String, Object>>> menus(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return R.success(service.menus(keyword, status));
    }

    @PostMapping("/menus")
    @RequiresPermission("system:menu:add")
    @OperLog(module = "菜单管理", action = "新增")
    public R<IdResponse> createMenu(@RequestBody MenuWriteRequest request) {
        return R.success(service.createMenu(request));
    }

    @PutMapping("/menus/{id}")
    @RequiresPermission("system:menu:edit")
    @OperLog(module = "菜单管理", action = "修改")
    public R<Void> updateMenu(@PathVariable Long id, @RequestBody MenuWriteRequest request) {
        service.updateMenu(id, request);
        return R.success(null);
    }

    @DeleteMapping("/menus/{id}")
    @RequiresPermission("system:menu:remove")
    @OperLog(module = "菜单管理", action = "删除")
    public R<Void> deleteMenu(@PathVariable Long id) {
        service.deleteMenu(id);
        return R.success(null);
    }

    @GetMapping("/depts/export")
    @RequiresPermission("system:dept:list")
    public ResponseEntity<String> exportDepts(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return csv("depts.csv", service.exportDepts(keyword, status));
    }

    @GetMapping("/depts/tree")
    @RequiresPermission("system:dept:list")
    public R<List<Map<String, Object>>> depts(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return R.success(service.depts(keyword, status));
    }

    @PostMapping("/depts")
    @RequiresPermission("system:dept:add")
    @OperLog(module = "部门管理", action = "新增")
    public R<IdResponse> createDept(@RequestBody DeptWriteRequest request) {
        return R.success(service.createDept(request));
    }

    @PutMapping("/depts/{id}")
    @RequiresPermission("system:dept:edit")
    @OperLog(module = "部门管理", action = "修改")
    public R<Void> updateDept(@PathVariable Long id, @RequestBody DeptWriteRequest request) {
        service.updateDept(id, request);
        return R.success(null);
    }

    @DeleteMapping("/depts/{id}")
    @RequiresPermission("system:dept:remove")
    @OperLog(module = "部门管理", action = "删除")
    public R<Void> deleteDept(@PathVariable Long id) {
        service.deleteDept(id);
        return R.success(null);
    }

    @GetMapping("/posts/export")
    @RequiresPermission("system:post:list")
    public ResponseEntity<String> exportPosts(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return csv("posts.csv", service.exportPosts(keyword, status));
    }

    @GetMapping("/posts")
    @RequiresPermission("system:post:list")
    public R<PageResult<Map<String, Object>>> posts(
            PageQuery query,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return R.success(service.posts(query, keyword, status));
    }

    @PostMapping("/posts")
    @RequiresPermission("system:post:add")
    @OperLog(module = "岗位管理", action = "新增")
    public R<IdResponse> createPost(@RequestBody PostWriteRequest request) {
        return R.success(service.createPost(request));
    }

    @PutMapping("/posts/{id}")
    @RequiresPermission("system:post:edit")
    @OperLog(module = "岗位管理", action = "修改")
    public R<Void> updatePost(@PathVariable Long id, @RequestBody PostWriteRequest request) {
        service.updatePost(id, request);
        return R.success(null);
    }

    @DeleteMapping("/posts/{id}")
    @RequiresPermission("system:post:remove")
    @OperLog(module = "岗位管理", action = "删除")
    public R<Void> deletePost(@PathVariable Long id) {
        service.deletePost(id);
        return R.success(null);
    }

    @GetMapping("/dict/types/export")
    @RequiresPermission("system:dict:list")
    public ResponseEntity<String> exportDictTypes(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return csv("dict-types.csv", service.exportDictTypes(keyword, status));
    }

    @GetMapping("/dict/types")
    @RequiresPermission("system:dict:list")
    public R<PageResult<Map<String, Object>>> dictTypes(
            PageQuery query,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status
    ) {
        return R.success(service.dictTypes(query, keyword, status));
    }

    @GetMapping("/dict/options/{dictType}")
    public R<List<Map<String, Object>>> dictOptions(@PathVariable String dictType) {
        return R.success(service.dictOptions(dictType));
    }

    @GetMapping("/dict/data/{dictType}")
    @RequiresPermission("system:dict:list")
    public R<List<Map<String, Object>>> dictData(@PathVariable String dictType) {
        return R.success(service.dictData(dictType));
    }

    @PostMapping("/dict/types")
    @RequiresPermission("system:dict:add")
    @OperLog(module = "字典管理", action = "新增字典类型")
    public R<IdResponse> createDictType(@RequestBody DictTypeWriteRequest request) {
        return R.success(service.createDictType(request));
    }

    @PutMapping("/dict/types/{id}")
    @RequiresPermission("system:dict:edit")
    @OperLog(module = "字典管理", action = "修改字典类型")
    public R<Void> updateDictType(@PathVariable Long id, @RequestBody DictTypeWriteRequest request) {
        service.updateDictType(id, request);
        return R.success(null);
    }

    @DeleteMapping("/dict/types/{id}")
    @RequiresPermission("system:dict:remove")
    @OperLog(module = "字典管理", action = "删除字典类型")
    public R<Void> deleteDictType(@PathVariable Long id) {
        service.deleteDictType(id);
        return R.success(null);
    }

    @PostMapping("/dict/data")
    @RequiresPermission("system:dict:add")
    @OperLog(module = "字典管理", action = "新增字典数据")
    public R<IdResponse> createDictData(@RequestBody DictDataWriteRequest request) {
        return R.success(service.createDictData(request));
    }

    @PutMapping("/dict/data/{id}")
    @RequiresPermission("system:dict:edit")
    @OperLog(module = "字典管理", action = "修改字典数据")
    public R<Void> updateDictData(@PathVariable Long id, @RequestBody DictDataWriteRequest request) {
        service.updateDictData(id, request);
        return R.success(null);
    }

    @DeleteMapping("/dict/data/{id}")
    @RequiresPermission("system:dict:remove")
    @OperLog(module = "字典管理", action = "删除字典数据")
    public R<Void> deleteDictData(@PathVariable Long id) {
        service.deleteDictData(id);
        return R.success(null);
    }

    @GetMapping("/configs/export")
    @RequiresPermission("system:config:list")
    public ResponseEntity<String> exportConfigs(@RequestParam(required = false) String keyword) {
        return csv("configs.csv", service.exportConfigs(keyword));
    }

    @GetMapping("/configs")
    @RequiresPermission("system:config:list")
    public R<PageResult<Map<String, Object>>> configs(
            PageQuery query,
            @RequestParam(required = false) String keyword
    ) {
        return R.success(service.configs(query, keyword));
    }

    @PostMapping("/configs")
    @RequiresPermission("system:config:add")
    @OperLog(module = "参数配置", action = "新增")
    public R<IdResponse> createConfig(@RequestBody ConfigWriteRequest request) {
        return R.success(service.createConfig(request));
    }

    @PutMapping("/configs/{id}")
    @RequiresPermission("system:config:edit")
    @OperLog(module = "参数配置", action = "修改")
    public R<Void> updateConfig(@PathVariable Long id, @RequestBody ConfigWriteRequest request) {
        service.updateConfig(id, request);
        return R.success(null);
    }

    @DeleteMapping("/configs/{id}")
    @RequiresPermission("system:config:remove")
    @OperLog(module = "参数配置", action = "删除")
    public R<Void> deleteConfig(@PathVariable Long id) {
        service.deleteConfig(id);
        return R.success(null);
    }
}
