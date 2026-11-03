package com.dramafactory.service.video;

import java.util.ArrayList;
import java.util.List;

/**
 * 视频请求参数校验器。
 *
 * 约定：
 * - validate 返回空列表表示校验通过，不拦截。
 * - validate 返回非空列表表示校验不通过，列表里每一条都是一个中文的违规描述。
 * - model 为 null，或者 model.getConstraints() 为 null 时，说明没有约束可依，直接返回空列表。
 * - 其余情况把校验交给 model.getConstraints().violations(prompt, seconds)。
 *
 * 这个类是纯函数类，不依赖 Spring，也不持有任何状态。
 */
public class VideoRequestValidator {

    public List<String> validate(ProviderDescriptor.DescriptorModel model, String prompt, int seconds) {
        if (model == null) {
            return new ArrayList<String>();
        }
        ProviderDescriptor.DescriptorModel.DescriptorConstraints constraints = model.getConstraints();
        if (constraints == null) {
            return new ArrayList<String>();
        }
        List<String> result = constraints.violations(prompt, seconds);
        if (result == null) {
            return new ArrayList<String>();
        }
        return result;
    }
}