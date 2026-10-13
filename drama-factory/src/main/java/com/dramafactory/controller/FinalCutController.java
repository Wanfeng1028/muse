package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.FinalCutService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 成片剪辑控制器。
 * 提供针对剧集成片的同步剪辑、列表查询与详情查询接口。
 */
@RestController
@RequestMapping("/api")
@Tag(name = "FinalCuts", description = "剧集成片剪辑与人工质检接口")
public class FinalCutController {

    private final FinalCutService finalCutService;

    /**
     * 构造器注入 FinalCutService。
     *
     * @param finalCutService 成片剪辑服务
     */
    public FinalCutController(FinalCutService finalCutService) {
        this.finalCutService = finalCutService;
    }

    /**
     * 对指定剧集同步执行成片剪辑，可能耗时较长。
     *
     * @param episodeId 剧集 ID
     * @return 剪辑结果
     */
    @PostMapping("/episodes/{episodeId}/final-cuts")
    @Operation(summary = "执行成片剪辑")
    public ResponseEntity<Records.FinalCutResponse> createFinalCut(@PathVariable Long episodeId) {
        Records.FinalCutResponse response = finalCutService.buildFinalCut(episodeId);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    /**
     * 查询指定剧集下的所有成片剪辑记录。
     *
     * @param episodeId 剧集 ID
     * @return 成片剪辑列表
     */
    @GetMapping("/episodes/{episodeId}/final-cuts")
    @Operation(summary = "查询剧集下的成片剪辑列表")
    public List<Records.FinalCutResponse> listFinalCutsByEpisode(@PathVariable Long episodeId) {
        return finalCutService.listByEpisode(episodeId);
    }

    /**
     * 根据 ID 查询成片剪辑详情。
     *
     * @param id 成片剪辑 ID
     * @return 成片剪辑详情
     */
    @GetMapping("/final-cuts/{id}")
    @Operation(summary = "按 ID 查询成片剪辑")
    public Records.FinalCutResponse getFinalCut(@PathVariable Long id) {
        return finalCutService.get(id);
    }

    /**
     * 成片人工质检：通过（APPROVED）→ 剧集 REVIEWED；打回（REJECTED）→ 剧集回退 SCRIPTED 返工。
     *
     * @param id      成片 ID
     * @param request 质检结论与备注
     * @return 更新后的成片详情
     */
    @PostMapping("/final-cuts/{id}/qc")
    @Operation(summary = "提交成片人工质检结论")
    public Records.FinalCutResponse qcFinalCut(@PathVariable Long id,
                                               @Valid @RequestBody Records.QcRequest request) {
        return finalCutService.qc(id, request);
    }
}
