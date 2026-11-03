package com.dramafactory.service;

import com.dramafactory.repository.SkillInstallRepository;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.repository.SkillVersionRepository;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@ExtendWith(MockitoExtension.class)
class SkillServiceV221ETest {

    @Mock
    private SkillRepository skillRepository;

    @Mock
    private SkillVersionRepository skillVersionRepository;

    @Mock
    private SkillInstallRepository skillInstallRepository;

    @Mock
    private SkillRatingRepository skillRatingRepository;

    @InjectMocks
    private SkillService skillService;

    @Test
    void publishVersion_nullPromptTemplate_throwsIllegalArgumentException() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(1L, "1.0.1", null, "changelog"));
        assertEquals("promptTemplate 不能为空", ex.getMessage());
    }
}
