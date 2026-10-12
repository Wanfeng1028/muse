package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.CharacterService;
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
public class CharacterController {

    private final CharacterService characterService;

    public CharacterController(CharacterService characterService) {
        this.characterService = characterService;
    }

    @GetMapping("/api/projects/{projectId}/characters")
    public List<Records.CharacterResponse> listByProject(@PathVariable Long projectId) {
        return characterService.listByProject(projectId);
    }

    @PostMapping("/api/projects/{projectId}/characters")
    public ResponseEntity<Records.CharacterResponse> create(
            @PathVariable Long projectId,
            @Valid @RequestBody Records.CharacterRequest request) {
        Records.CharacterResponse response = characterService.create(projectId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PutMapping("/api/characters/{id}")
    public Records.CharacterResponse update(
            @PathVariable Long id,
            @Valid @RequestBody Records.CharacterRequest request) {
        return characterService.update(id, request);
    }

    @DeleteMapping("/api/characters/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        characterService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
