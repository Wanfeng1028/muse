'use strict';

// BotsRouter fallback adapter (OpenAI-compatible chat completions).
// Base URL and key come only from environment config:
//   BOTSROUTER_BASE_URL (default https://api.botsarena.tech/v1)
//   BOTSROUTER_API_KEY  (required; never hardcode, never log)
//   BOTSROUTER_CHAT_MODEL / BOTSROUTER_IMAGE_MODEL (config overrides)
// Uses only Node built-in https so the function needs no extra dependency.

const https = require('https');

const DEFAULT_BASE_URL = 'https://api.botsarena.tech/v1';

function buildChatRequest(model, messages) {
  return {
    model: model,
    messages: messages,
    temperature: 0.7
  };
}

function parseChatResponse(body) {
  const choice = body && body.choices && body.choices[0];
  const text = choice && choice.message ? choice.message.content : '';
  return {
    text: typeof text === 'string' ? text : '',
    usage: (body && body.usage) || null,
    rawModel: (body && body.model) || null
  };
}

function postJson(baseUrl, path, apiKey, payload, timeoutMs) {
  return new Promise(function (resolve, reject) {
    const url = new URL(baseUrl.replace(/\/$/, '') + path);
    const body = JSON.stringify(payload);
    const req = https.request({
      method: 'POST',
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + apiKey,
        'Content-Length': Buffer.byteLength(body)
      },
      timeout: timeoutMs || 120000
    }, function (res) {
      let chunks = '';
      res.on('data', function (c) { chunks += c; });
      res.on('end', function () {
        let parsed = null;
        try { parsed = JSON.parse(chunks); } catch (e) { parsed = null; }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const err = new Error('BOTSROUTER_HTTP_' + res.statusCode);
          err.statusCode = res.statusCode;
          err.body = parsed || chunks;
          reject(err);
          return;
        }
        resolve(parsed);
      });
    });
    req.on('timeout', function () { req.destroy(new Error('BOTSROUTER_TIMEOUT')); });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function chatCompletions(options) {
  const apiKey = options.apiKey;
  if (!apiKey) {
    const err = new Error('BOTSROUTER_API_KEY_NOT_CONFIGURED');
    err.code = 'BOTSROUTER_API_KEY_NOT_CONFIGURED';
    throw err;
  }
  const baseUrl = options.baseUrl || DEFAULT_BASE_URL;
  const payload = buildChatRequest(options.model, options.messages);
  const body = await postJson(baseUrl, '/chat/completions', apiKey, payload);
  return parseChatResponse(body);
}

// Image fallback: POST /v1/images/generations (OpenAI-compatible shape).
// Only attempted when a BotsRouter image model is configured; the seed
// leaves it empty on purpose rather than inventing a model name.
async function imageGenerations(options) {
  const apiKey = options.apiKey;
  if (!apiKey) {
    const err = new Error('BOTSROUTER_API_KEY_NOT_CONFIGURED');
    err.code = 'BOTSROUTER_API_KEY_NOT_CONFIGURED';
    throw err;
  }
  if (!options.model) {
    const err = new Error('BOTSROUTER_IMAGE_MODEL_NOT_CONFIGURED');
    err.code = 'BOTSROUTER_IMAGE_MODEL_NOT_CONFIGURED';
    throw err;
  }
  const baseUrl = options.baseUrl || DEFAULT_BASE_URL;
  const body = await postJson(baseUrl, '/images/generations', apiKey, {
    model: options.model,
    prompt: options.prompt,
    size: options.size || '1024x1024'
  }, 300000);
  const item = body && body.data && body.data[0];
  if (!item || !item.url) {
    throw new Error('BOTSROUTER_IMAGE_NO_URL');
  }
  return { url: item.url, revisedPrompt: item.revised_prompt || null };
}

module.exports = {
  DEFAULT_BASE_URL: DEFAULT_BASE_URL,
  buildChatRequest: buildChatRequest,
  parseChatResponse: parseChatResponse,
  chatCompletions: chatCompletions,
  imageGenerations: imageGenerations
};
