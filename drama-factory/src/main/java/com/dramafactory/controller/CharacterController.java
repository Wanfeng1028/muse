package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.CharacterService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@Tag(name = "Characters", description = "项目角色的增删改查接口")
public class CharacterController {

    private final CharacterService characterService;

    public CharacterController(CharacterService characterService) {
        this.characterService = characterService;
    }

    @GetMapping("/api/projects/{projectId}/characters")
    @Operation(summary = "按项目查询角色列表")
    public List<Records.CharacterResponse> listByProject(@PathVariable Long projectId) {
        return characterService.listByProject(projectId);
    }

    @PostMapping("/api/projects/{projectId}/characters")
    @Operation(summary = "创建角色")
    public ResponseEntity<Records.CharacterResponse> create(
            @PathVariable Long projectId,
            @Valid @RequestBody Records.CharacterRequest request) {
        Records.CharacterResponse response = characterService.create(projectId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PutMapping("/api/characters/{id}")
    @Operation(summary = "更新角色")
    public Records.CharacterResponse update(
            @PathVariable Long id,
            @Valid @RequestBody Records.CharacterRequest request) {
        return characterService.update(id, request);
    }

    @DeleteMapping("/api/characters/{id}")
    @Operation(summary = "删除角色")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        characterService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
