/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import { Config } from "@remotion/cli/config";

Config.setRspack(true);
// PNG keeps the fine star dust from being smeared by JPEG chroma subsampling.
Config.setVideoImageFormat("png");
Config.setOverwriteOutput(true);
