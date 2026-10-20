package com.dramafactory.controller;

import com.dramafactory.service.video.ProviderDescriptor;
import com.dramafactory.service.video.ProviderDescriptorRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/api/descriptor-providers")
public class DescriptorProviderController {

    private final ProviderDescriptorRegistry registry;

    public DescriptorProviderController(ProviderDescriptorRegistry registry) {
        this.registry = registry;
    }

    public record ConstraintView(Integer maxPromptChars, Integer minDurationSeconds, Integer maxDurationSeconds,
                                 List<String> resolutions, List<String> aspectRatios, Integer maxReferenceImages,
                                 String source) {
    }

    public record ModelView(String id, String label, String type, ConstraintView constraints) {
    }

    public record ProviderView(String id, String label, List<ModelView> models) {
    }

    @GetMapping
    public List<ProviderView> list() {
        List<ProviderView> result = new ArrayList<>();
        for (ProviderDescriptor descriptor : registry.all()) {
            List<ModelView> models = new ArrayList<>();
            if (descriptor.getModels() != null) {
                for (ProviderDescriptor.DescriptorModel model : descriptor.getModels()) {
                    models.add(new ModelView(model.getId(), model.getLabel(), model.getType(),
                            toConstraintView(model.getConstraints())));
                }
            }
            result.add(new ProviderView(descriptor.getId(), descriptor.getLabel(), models));
        }
        return result;
    }

    private static ConstraintView toConstraintView(ProviderDescriptor.DescriptorModel.DescriptorConstraints c) {
        if (c == null) {
            return null;
        }
        return new ConstraintView(c.getMaxPromptChars(), c.getMinDurationSeconds(), c.getMaxDurationSeconds(),
                c.getResolutions(), c.getAspectRatios(), c.getMaxReferenceImages(), c.getSource());
    }
}