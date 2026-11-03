"use strict";

// electron/speech/stt-worker.ts
var import_node_worker_threads = require("node:worker_threads");

// electron/speech/stt-audio-resample.ts
function resampleToRate(samples, inputSampleRate, outputSampleRate) {
  if (samples.length === 0 || !Number.isFinite(inputSampleRate) || !Number.isFinite(outputSampleRate) || inputSampleRate <= 0 || outputSampleRate <= 0 || inputSampleRate === outputSampleRate) {
    return samples;
  }
  const outputLength = Math.max(
    1,
    Math.round(samples.length * outputSampleRate / inputSampleRate)
  );
  const output = new Float32Array(outputLength);
  const ratio = inputSampleRate / outputSampleRate;
  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = i * ratio;
    const left = Math.floor(sourceIndex);
    const right = Math.min(left + 1, samples.length - 1);
    const weight = sourceIndex - left;
    output[i] = samples[left] * (1 - weight) + samples[right] * weight;
  }
  return output;
}

// electron/speech/stt-offline-audio-chunker.ts
var OFFLINE_DECODE_CHUNK_SECONDS = 30;
var SPLIT_SEARCH_SECONDS = 5;
var SPLIT_ENERGY_WINDOW_SECONDS = 0.1;
var OfflineAudioChunker = class {
  constructor(sampleRate) {
    this.buffered = [];
    this.bufferedSamples = 0;
    this.chunkSampleLimit = Math.max(1, Math.round(OFFLINE_DECODE_CHUNK_SECONDS * sampleRate));
    this.splitSearchSamples = Math.round(SPLIT_SEARCH_SECONDS * sampleRate);
    this.energyWindowSamples = Math.max(1, Math.round(SPLIT_ENERGY_WINDOW_SECONDS * sampleRate));
  }
  /** Buffers samples and returns any full chunks now ready to decode. */
  push(samples) {
    if (samples.length === 0) {
      return [];
    }
    this.buffered.push(samples);
    this.bufferedSamples += samples.length;
    const ready = [];
    while (this.bufferedSamples >= this.chunkSampleLimit) {
      const combined = this.combineBuffered();
      const splitIndex = this.findQuietSplitIndex(combined);
      ready.push(combined.slice(0, splitIndex));
      const tail = combined.slice(splitIndex);
      this.buffered = tail.length > 0 ? [tail] : [];
      this.bufferedSamples = tail.length;
    }
    return ready;
  }
  /** Returns all remaining buffered audio (any length below the chunk limit). */
  flush() {
    if (this.bufferedSamples === 0) {
      return null;
    }
    const combined = this.combineBuffered();
    this.buffered = [];
    this.bufferedSamples = 0;
    return combined;
  }
  combineBuffered() {
    if (this.buffered.length === 1) {
      return this.buffered[0];
    }
    const combined = new Float32Array(this.bufferedSamples);
    let offset = 0;
    for (const chunk of this.buffered) {
      combined.set(chunk, offset);
      offset += chunk.length;
    }
    return combined;
  }
  findQuietSplitIndex(samples) {
    const limit = Math.min(this.chunkSampleLimit, samples.length);
    const window = this.energyWindowSamples;
    const searchStart = Math.max(0, limit - this.splitSearchSamples);
    const hop = Math.max(1, Math.floor(window / 2));
    let bestIndex = limit;
    let bestEnergy = Infinity;
    for (let start = searchStart; start + window <= limit; start += hop) {
      let energy = 0;
      for (let i = start; i < start + window; i += 1) {
        energy += samples[i] * samples[i];
      }
      if (energy < bestEnergy) {
        bestEnergy = energy;
        bestIndex = start + Math.floor(window / 2);
      }
    }
    return Math.max(1, bestIndex);
  }
};

// electron/speech/stt-worker.ts
var sherpa = null;
var recognizer = null;
var stream = null;
var isStreaming = false;
var offlineChunker = null;
var offlineSampleRate = 16e3;
function loadSherpa() {
  const modulePath = import_node_worker_threads.workerData?.sherpaModulePath;
  if (!modulePath) {
    throw new Error("workerData.sherpaModulePath is required");
  }
  return require(modulePath);
}
function resolveFile(files, role, modelDir, ext = ".onnx") {
  const match = files.find((f) => f.includes(role) && f.endsWith(ext));
  if (!match) {
    throw new Error(`No *${role}*${ext} found in model files: ${files.join(", ")}`);
  }
  return `${modelDir}/${match}`;
}
function resolveTokens(files, modelDir) {
  const match = files.find((f) => f.endsWith("tokens.txt"));
  if (!match) {
    throw new Error(`No *tokens.txt found in model files: ${files.join(", ")}`);
  }
  return `${modelDir}/${match}`;
}
function handleInit(msg) {
  try {
    sherpa = loadSherpa();
    const { modelDir, modelType, streaming, sampleRate, files } = msg;
    isStreaming = streaming;
    offlineSampleRate = sampleRate;
    offlineChunker = streaming ? null : new OfflineAudioChunker(sampleRate);
    const tokens = resolveTokens(files, modelDir);
    if (streaming && modelType === "transducer") {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          transducer: {
            encoder: resolveFile(files, "encoder", modelDir),
            decoder: resolveFile(files, "decoder", modelDir),
            joiner: resolveFile(files, "joiner", modelDir)
          },
          tokens,
          numThreads: 1,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search",
        enableEndpoint: 1,
        rule1MinTrailingSilence: 2.4,
        rule2MinTrailingSilence: 1.2,
        rule3MinUtteranceLength: 20
      };
      recognizer = sherpa.createOnlineRecognizer(config);
      stream = sherpa.createOnlineStream(recognizer);
    } else if (streaming && modelType === "paraformer") {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          paraformer: {
            encoder: resolveFile(files, "encoder", modelDir),
            decoder: resolveFile(files, "decoder", modelDir)
          },
          tokens,
          numThreads: 1,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search",
        enableEndpoint: 1,
        rule1MinTrailingSilence: 2.4,
        rule2MinTrailingSilence: 1.2,
        rule3MinUtteranceLength: 20
      };
      recognizer = sherpa.createOnlineRecognizer(config);
      stream = sherpa.createOnlineStream(recognizer);
    } else if (modelType === "whisper") {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          whisper: {
            encoder: resolveFile(files, "encoder", modelDir),
            decoder: resolveFile(files, "decoder", modelDir)
          },
          tokens,
          numThreads: 2,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search"
      };
      recognizer = sherpa.createOfflineRecognizer(config);
      stream = sherpa.createOfflineStream(recognizer);
    } else if (modelType === "senseVoice") {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          senseVoice: {
            model: resolveFile(files, "model", modelDir),
            // Empty string = auto-detect language (zh/en/ja/ko/yue).
            language: "",
            // Inverse text normalization — emits punctuation + digits.
            useInverseTextNormalization: 1
          },
          tokens,
          numThreads: 2,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search"
      };
      recognizer = sherpa.createOfflineRecognizer(config);
      stream = sherpa.createOfflineStream(recognizer);
    } else if (modelType === "paraformer") {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          paraformer: {
            model: resolveFile(files, "model", modelDir)
          },
          tokens,
          numThreads: 2,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search"
      };
      recognizer = sherpa.createOfflineRecognizer(config);
      stream = sherpa.createOfflineStream(recognizer);
    } else {
      const config = {
        featConfig: { sampleRate, featureDim: 80 },
        modelConfig: {
          transducer: {
            encoder: resolveFile(files, "encoder", modelDir),
            decoder: resolveFile(files, "decoder", modelDir),
            joiner: resolveFile(files, "joiner", modelDir)
          },
          tokens,
          numThreads: 2,
          provider: "cpu",
          debug: 0
        },
        decodingMethod: "greedy_search"
      };
      recognizer = sherpa.createOfflineRecognizer(config);
      stream = sherpa.createOfflineStream(recognizer);
    }
    import_node_worker_threads.parentPort?.postMessage({ type: "ready" });
  } catch (err) {
    import_node_worker_threads.parentPort?.postMessage({ type: "error", error: String(err) });
  }
}
function decodeOfflineChunk(samples) {
  try {
    sherpa.acceptWaveformOffline(stream, { sampleRate: offlineSampleRate, samples });
    sherpa.decodeOfflineStream(recognizer, stream);
    const resultJson = sherpa.getOfflineStreamResultAsJson(stream);
    const result = JSON.parse(resultJson);
    return result?.text?.trim() ?? "";
  } finally {
    if (sherpa && recognizer) {
      stream = sherpa.createOfflineStream(recognizer);
    }
  }
}
function resetOfflineSessionState() {
  try {
    offlineChunker = new OfflineAudioChunker(offlineSampleRate);
    if (sherpa && recognizer) {
      stream = sherpa.createOfflineStream(recognizer);
    }
  } catch {
  }
}
function handleFeed(msg) {
  if (!recognizer || !stream) {
    return;
  }
  try {
    const inputRate = msg.sampleRate || offlineSampleRate;
    const samples = resampleToRate(msg.samples, inputRate, offlineSampleRate);
    if (isStreaming) {
      sherpa.acceptWaveformOnline(stream, { sampleRate: offlineSampleRate, samples });
      while (sherpa.isOnlineStreamReady(recognizer, stream)) {
        sherpa.decodeOnlineStream(recognizer, stream);
      }
      const resultJson = sherpa.getOnlineStreamResultAsJson(recognizer, stream);
      const result = JSON.parse(resultJson);
      const text = result?.text?.trim();
      if (text) {
        import_node_worker_threads.parentPort?.postMessage({ type: "partial", text });
      }
      if (sherpa.isEndpoint(recognizer, stream)) {
        const finalText = result?.text?.trim();
        if (finalText) {
          import_node_worker_threads.parentPort?.postMessage({ type: "final", text: finalText });
        }
        sherpa.reset(recognizer, stream);
      }
    } else {
      const readyChunks = offlineChunker?.push(new Float32Array(samples)) ?? [];
      let firstError = null;
      for (const chunk of readyChunks) {
        try {
          const text = decodeOfflineChunk(chunk);
          if (text) {
            import_node_worker_threads.parentPort?.postMessage({ type: "final", text });
          }
        } catch (err) {
          firstError ??= err;
        }
      }
      if (firstError) {
        throw firstError;
      }
    }
  } catch (err) {
    import_node_worker_threads.parentPort?.postMessage({ type: "error", error: String(err) });
  }
}
function handleStop() {
  if (!recognizer || !stream) {
    import_node_worker_threads.parentPort?.postMessage({ type: "stopped" });
    return;
  }
  try {
    if (isStreaming) {
      sherpa.inputFinished(stream);
      while (sherpa.isOnlineStreamReady(recognizer, stream)) {
        sherpa.decodeOnlineStream(recognizer, stream);
      }
      const resultJson = sherpa.getOnlineStreamResultAsJson(recognizer, stream);
      const result = JSON.parse(resultJson);
      const text = result?.text?.trim();
      if (text) {
        import_node_worker_threads.parentPort?.postMessage({ type: "final", text });
      }
      stream = sherpa.createOnlineStream(recognizer);
    } else {
      const remaining = offlineChunker?.flush();
      if (remaining && remaining.length > 0) {
        const text = decodeOfflineChunk(remaining);
        if (text) {
          import_node_worker_threads.parentPort?.postMessage({ type: "final", text });
        }
      }
      resetOfflineSessionState();
    }
  } catch (err) {
    if (!isStreaming) {
      resetOfflineSessionState();
    }
    import_node_worker_threads.parentPort?.postMessage({ type: "error", error: String(err) });
  } finally {
    import_node_worker_threads.parentPort?.postMessage({ type: "stopped" });
  }
}
function handleTeardown() {
  stream = null;
  recognizer = null;
  sherpa = null;
  offlineChunker = null;
  process.exit(0);
}
import_node_worker_threads.parentPort?.on("message", (msg) => {
  switch (msg.type) {
    case "init":
      handleInit(msg);
      break;
    case "feed":
      handleFeed(msg);
      break;
    case "stop":
      handleStop();
      break;
    case "teardown":
      handleTeardown();
      break;
  }
});
