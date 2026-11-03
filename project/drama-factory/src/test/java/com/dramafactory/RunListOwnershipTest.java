package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.model.Run;
import com.dramafactory.service.RunService;
import com.dramafactory.model.RunStatus;
import com.dramafactory.model.DramaProject;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.service.ProjectService;

import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:runlistownership;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class RunListOwnershipTest {

    @Autowired
    private RunService runService;

    @Autowired
    private RunRepository runRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private ProjectService projectService;

    @BeforeEach
    void cleanUp() {
        runRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void listRuns_shouldExcludeForeignRunsAndMatchStats() {
        Records.ProjectResponse ownProject =
                projectService.create(new Records.ProjectRequest("本人项目", null, null, null, null));

        DramaProject foreignProject = new DramaProject();
        foreignProject.setTitle("他人项目");
        foreignProject.setOwnerId("foreign-user");
        projectRepository.save(foreignProject);

        Run ownRun1 = new Run();
        ownRun1.setGoal("本人运行1");
        ownRun1.setStatus(RunStatus.PLANNED);
        ownRun1.setProjectId(ownProject.id());
        runRepository.save(ownRun1);

        Run ownRun2 = new Run();
        ownRun2.setGoal("本人运行2");
        ownRun2.setStatus(RunStatus.PLANNED);
        ownRun2.setProjectId(ownProject.id());
        runRepository.save(ownRun2);

        Run foreignRun = new Run();
        foreignRun.setGoal("他人运行");
        foreignRun.setStatus(RunStatus.PLANNED);
        foreignRun.setProjectId(foreignProject.getId());
        runRepository.save(foreignRun);

        Run orphanRun = new Run();
        orphanRun.setGoal("孤儿运行");
        orphanRun.setStatus(RunStatus.PLANNED);
        runRepository.save(orphanRun);

        assertEquals(2, runService.listRuns().size());
        Set<Long> returnedIds = runService.listRuns().stream()
                .map(Run::getId)
                .collect(Collectors.toSet());
        assertEquals(Set.of(ownRun1.getId(), ownRun2.getId()), returnedIds);
        assertEquals(2, runService.stats().totalRuns());
        assertTrue(runService.listRuns().stream()
                .noneMatch(r -> r.getId().equals(foreignRun.getId()) || r.getId().equals(orphanRun.getId())));
    }
}