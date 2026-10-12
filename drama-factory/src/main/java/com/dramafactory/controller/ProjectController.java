package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.ProjectService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
public class ProjectController {

    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @PostMapping("/api/projects")
    @ResponseStatus(HttpStatus.CREATED)
    public Records.ProjectResponse create(@Valid @RequestBody Records.ProjectRequest request) {
        return projectService.create(request);
    }

    @GetMapping("/api/projects")
    public List<Records.ProjectResponse> list() {
        return projectService.list();
    }

    @GetMapping("/api/projects/{id}")
    public Records.ProjectResponse get(@PathVariable Long id) {
        return projectService.get(id);
    }

    @PutMapping("/api/projects/{id}")
    public Records.ProjectResponse update(@PathVariable Long id,
                                          @Valid @RequestBody Records.ProjectRequest request) {
        return projectService.update(id, request);
    }

    @DeleteMapping("/api/projects/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        projectService.delete(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/stats")
    public Records.StatsResponse stats() {
        return projectService.stats();
    }
}
