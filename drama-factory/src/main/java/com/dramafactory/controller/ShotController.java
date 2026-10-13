package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.ScriptSplitterService;
import com.dramafactory.service.ShotService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 分镜（Shot）相关接口控制器。
 * 提供分镜的查询、新增、修改、删除以及排序功能。
 */
@RestController
@RequestMapping("/api")
public class ShotController {

    private final ShotService shotService;
    private final ScriptSplitterService scriptSplitterService;

    /**
     * 构造器注入分镜服务与剧本拆分服务。
     */
    public ShotController(ShotService shotService, ScriptSplitterService scriptSplitterService) {
        this.shotService = shotService;
        this.scriptSplitterService = scriptSplitterService;
    }

    /**
     * 查询指定剧集下的所有分镜，按镜头序号升序排列。
     *
     * @param episodeId 剧集 ID
     * @return 分镜响应列表
     */
    @GetMapping("/episodes/{episodeId}/shots")
    public List<Records.ShotResponse> listShots(@PathVariable Long episodeId) {
        return shotService.listByEpisode(episodeId);
    }

    /**
     * 在指定剧集下新增一个分镜。
     *
     * @param episodeId 剧集 ID
     * @param request   分镜请求体
     * @return 201 状态及新建的分镜响应
     */
    @PostMapping("/episodes/{episodeId}/shots")
    public ResponseEntity<Records.ShotResponse> createShot(@PathVariable Long episodeId,
                                                           @Valid @RequestBody Records.ShotRequest request) {
        Records.ShotResponse response = shotService.create(episodeId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /**
     * 更新指定分镜信息。
     *
     * @param id      分镜 ID
     * @param request 分镜请求体
     * @return 更新后的分镜响应
     */
    @PutMapping("/shots/{id}")
    public Records.ShotResponse updateShot(@PathVariable Long id,
                                           @Valid @RequestBody Records.ShotRequest request) {
        return shotService.update(id, request);
    }

    /**
     * 删除指定分镜。
     *
     * @param id 分镜 ID
     * @return 204 无内容响应
     */
    @DeleteMapping("/shots/{id}")
    public ResponseEntity<Void> deleteShot(@PathVariable Long id) {
        shotService.delete(id);
        return ResponseEntity.noContent().build();
    }

    /**
     * 从剧本原文 AI 拆分分镜：粘贴剧本 → 大模型拆成结构化分镜 → 落库（替换该剧集旧分镜）。
     *
     * @param episodeId 剧集 ID
     * @param request   剧本原文
     * @return 新建的分镜列表
     */
    @PostMapping("/episodes/{episodeId}/shots/from-script")
    public ResponseEntity<List<Records.ShotResponse>> splitFromScript(
            @PathVariable Long episodeId,
            @Valid @RequestBody Records.ScriptSplitRequest request) {
        List<Records.ShotResponse> result =
                scriptSplitterService.splitFromScript(episodeId, request.scriptText());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    /**
     * 批量落库分镜（替换该剧集全部旧分镜）：供"AI 对话"页使用，
     * 用户在对话里逐镜调整确认后，前端把最终分镜数组直接发过来落库。
     *
     * @param episodeId 剧集 ID
     * @param request   确认后的分镜列表（景别/运镜为中文标签）
     * @return 新建的分镜列表
     */
    @PostMapping("/episodes/{episodeId}/shots/batch")
    public ResponseEntity<List<Records.ShotResponse>> replaceShots(
            @PathVariable Long episodeId,
            @Valid @RequestBody Records.ShotBatchRequest request) {
        List<Records.ShotResponse> result =
                scriptSplitterService.replaceShots(episodeId, request.shots());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    /**
     * 对指定剧集下的分镜重新排序。
     *
     * @param episodeId 剧集 ID
     * @param request   排序请求体，包含按顺序排列的分镜 ID 列表
     * @return 排序后的分镜响应列表
     */
    @PostMapping("/episodes/{episodeId}/shots/reorder")
    public List<Records.ShotResponse> reorderShots(@PathVariable Long episodeId,
                                                   @RequestBody Records.ReorderRequest request) {
        shotService.reorder(episodeId, request.shotIds());
        return shotService.listByEpisode(episodeId);
    }
}
