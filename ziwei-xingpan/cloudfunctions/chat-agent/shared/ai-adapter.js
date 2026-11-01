'use strict';

// AI adapter: primary CloudBase built-in models, fallback BotsRouter.
// Primary call shape follows the CloudBase docs (verified 2026-11-01):
//   const cloudbase = require('@cloudbase/node-sdk');
//   const app = cloudbase.init({ env: process.env.CLOUDBASE_ENV_ID });
//   const ai = app.ai();
//   const model = ai.createModel('cloudbase');
//   const result = await model.generateText({ model: 'deepseek-v4-flash', messages });
//   // result.text, result.usage
//   const imageModel = ai.createImageModel('hunyuan-image');
//   const res = await imageModel.generateImage({
//   //   model: 'HY-Image-3.0-Plus-4090-Tob-v1.0', prompt, size,
//   //   revise: { value: true }
//   // });
//   // res.data[0].url (valid 24h), res.data[0].revised_prompt
// The image model requires @cloudbase/node-sdk >= 3.18.3 (default sub-url
// config for HY-Image-3.0-Plus is built into that version).
// The adapter never invents text or an image: if both providers fail it
// throws AI_UNAVAILABLE and the caller returns that error to the client
// together with the degraded status, never a fabricated result.

const botsrouter = require('./botsrouter');

function cloudbaseEnvId() {
  return process.env.CLOUDBASE_ENV_ID || process.env.ENV_ID || process.env.TCB_ENV_ID || '';
}

function notConfigured(message) {
  const err = new Error(message);
  err.code = 'AI_NOT_CONFIGURED';
  return err;
}

// maxTokens is optional and only used by the chat-agent budget cap:
// when provided it is passed through to the provider (CloudBase
// generateText options; BotsRouter max_tokens). Callers that do not
// pass it (ai, aiImage) keep their exact current behavior.
async function cloudbaseChat(messages, model, maxTokens) {
  const envId = cloudbaseEnvId();
  if (!envId) {
    throw notConfigured('CLOUDBASE_ENV_ID_NOT_CONFIGURED');
  }
  let cloudbase;
  try {
    cloudbase = require('@cloudbase/node-sdk');
  } catch (e) {
    throw notConfigured('CLOUDBASE_NODE_SDK_NOT_INSTALLED');
  }
  const app = cloudbase.init({ env: envId });
  const ai = app.ai();
  const chatModel = ai.createModel('cloudbase');
  const genOptions = { model: model, messages: messages };
  if (typeof maxTokens === 'number' && maxTokens > 0) {
    genOptions.maxTokens = maxTokens;
  }
  const result = await chatModel.generateText(genOptions);
  if (!result || typeof result.text !== 'string') {
    throw new Error('CLOUDBASE_EMPTY_RESPONSE');
  }
  return { text: result.text, usage: result.usage || null };
}

async function cloudbaseImage(prompt, model, size) {
  const envId = cloudbaseEnvId();
  if (!envId) {
    throw notConfigured('CLOUDBASE_ENV_ID_NOT_CONFIGURED');
  }
  let cloudbase;
  try {
    cloudbase = require('@cloudbase/node-sdk');
  } catch (e) {
    throw notConfigured('CLOUDBASE_NODE_SDK_NOT_INSTALLED');
  }
  const app = cloudbase.init({ env: envId, timeout: 300000 });
  const ai = app.ai();
  const imageModel = ai.createImageModel('hunyuan-image');
  const res = await imageModel.generateImage({
    model: model, prompt: prompt, size: size || '1024x1024', revise: { value: true }
  });
  const item = res && res.data && res.data[0];
  if (!item || !item.url) {
    throw new Error('CLOUDBASE_IMAGE_NO_URL');
  }
  return { url: item.url, revisedPrompt: item.revised_prompt || null };
}

async function generateTextWithFallback(options) {
  const errors = [];
  if (!options.forceFallback) {
    try {
      const primary = await cloudbaseChat(options.messages, options.cloudbaseModel, options.maxTokens);
      return {
        text: primary.text, usage: primary.usage,
        provider: 'cloudbase', degraded: false, reason: null
      };
    } catch (e) {
      errors.push('cloudbase:' + (e.code || e.message));
    }
  } else {
    errors.push('cloudbase:skipped-by-quota-policy');
  }
  try {
    const fallback = await botsrouter.chatCompletions({
      apiKey: options.botsrouterApiKey,
      baseUrl: options.botsrouterBaseUrl,
      model: options.botsrouterModel,
      messages: options.messages,
      maxTokens: options.maxTokens
    });
    return {
      text: fallback.text, usage: fallback.usage,
      provider: 'botsrouter', degraded: true,
      reason: errors.join('; ')
    };
  } catch (e) {
    errors.push('botsrouter:' + (e.code || e.message));
  }
  const err = new Error('AI_UNAVAILABLE');
  err.code = 'AI_UNAVAILABLE';
  err.causes = errors;
  throw err;
}

async function generateImageWithFallback(options) {
  const errors = [];
  if (!options.forceFallback) {
    try {
      const primary = await cloudbaseImage(options.prompt, options.cloudbaseModel, options.size);
      return {
        url: primary.url, revisedPrompt: primary.revisedPrompt,
        provider: 'cloudbase', degraded: false, reason: null
      };
    } catch (e) {
      errors.push('cloudbase:' + (e.code || e.message));
    }
  } else {
    errors.push('cloudbase:skipped-by-quota-policy');
  }
  try {
    const fallback = await botsrouter.imageGenerations({
      apiKey: options.botsrouterApiKey,
      baseUrl: options.botsrouterBaseUrl,
      model: options.botsrouterModel,
      prompt: options.prompt,
      size: options.size
    });
    return {
      url: fallback.url, revisedPrompt: fallback.revisedPrompt,
      provider: 'botsrouter', degraded: true,
      reason: errors.join('; ')
    };
  } catch (e) {
    errors.push('botsrouter:' + (e.code || e.message));
  }
  const err = new Error('AI_IMAGE_UNAVAILABLE');
  err.code = 'AI_IMAGE_UNAVAILABLE';
  err.causes = errors;
  throw err;
}

module.exports = {
  cloudbaseEnvId: cloudbaseEnvId,
  cloudbaseChat: cloudbaseChat,
  cloudbaseImage: cloudbaseImage,
  generateTextWithFallback: generateTextWithFallback,
  generateImageWithFallback: generateImageWithFallback
};
