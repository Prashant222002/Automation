#!/usr/bin/env node
// NeuroTriage Advance Engine: long-form (1-2 hr+) chunked renderer.
// Uses HyperFrames' own distributed render primitives from @hyperframes/producer:
//   planV2  -> freezes the composition into a content-addressed plan
//   renderChunkV2 -> renders one chunk of frames (retry-safe, byte-identical)
//   assembleV2    -> stitches chunks into one video (closed-GOP concat, no re-encode)
//
// Usage (run from the repo root, after pipeline.py fetch/voice/captions/compose):
//   node focus/long_render.mjs plan              -> work/planv2/ + work/chunks.json
//   node focus/long_render.mjs chunk <index>     -> work/chunks/chunk-<index>.mp4
//   node focus/long_render.mjs assemble          -> work/render.mp4 (visuals only; audio is mixed by pipeline.py finish)
import { planV2, renderChunkV2, assembleV2, readPlanV2Manifest } from "@hyperframes/producer/distributed";
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

const WORK = resolve(process.env.FOCUS_WORK || "work");
const PROJ = join(WORK, "proj");
const PLAN = join(WORK, "planv2");
const CHUNKS = join(WORK, "chunks");

// Canvas and fps are read from spec.json only in the plan job (chunk/assemble jobs
// work from the frozen plan and do not need the spec).
function buildConfig() {
  const spec = JSON.parse(readFileSync(join(WORK, "spec.json"), "utf8"));
  const long = spec.format === "long";
  return {
    fps: 30,                                  // integer fps is required in distributed mode
    width: long ? 1920 : 1080,                // same canvas as the short pipeline
    height: long ? 1080 : 1920,
    format: "mp4",
    codec: "h264",
    quality: process.env.NT_QUALITY || "standard",
    // 9000 frames = 5 minutes at 30 fps per chunk. Tune after a timing test.
    chunkSize: Number(process.env.NT_CHUNK_FRAMES || 9000),
    maxParallelChunks: 200,                   // do not clamp the chunk count (GitHub matrix max is 256)
  };
}

const log = (...a) => console.log("[neurotriage-long]", ...a);

async function cmdPlan() {
  if (existsSync(PLAN)) throw new Error(`plan dir already exists: ${PLAN}`);
  const r = await planV2(PROJ, buildConfig(), PLAN);
  const m = readPlanV2Manifest(PLAN);
  const info = { chunkCount: m.chunkCount, totalFrames: m.totalFrames, planHash: r.planHash };
  writeFileSync(join(WORK, "chunks.json"), JSON.stringify(info, null, 1));
  log("plan ready:", JSON.stringify(info));
  // Matrix for GitHub Actions: [0, 1, ..., chunkCount-1]
  console.log(JSON.stringify([...Array(m.chunkCount).keys()]));
}

async function cmdChunk(indexArg) {
  const index = Number(indexArg);
  if (!Number.isInteger(index) || index < 0) throw new Error(`bad chunk index: ${indexArg}`);
  mkdirSync(CHUNKS, { recursive: true });
  const out = join(CHUNKS, `chunk-${index}.mp4`);
  await renderChunkV2(PLAN, index, out);
  log("chunk done:", index, out);
}

async function cmdAssemble() {
  const m = readPlanV2Manifest(PLAN);
  const paths = [];
  for (let i = 0; i < m.chunkCount; i++) {
    const p = join(CHUNKS, `chunk-${i}.mp4`);
    if (!existsSync(p)) throw new Error(`missing chunk ${i} (${p}). Re-run that chunk job.`);
    paths.push(p);
  }
  await assembleV2(PLAN, paths, join(WORK, "render.mp4"));
  log(`assembled ${paths.length} chunks -> ${join(WORK, "render.mp4")}`);
}

const [cmd, arg] = process.argv.slice(2);
try {
  if (cmd === "plan") await cmdPlan();
  else if (cmd === "chunk") await cmdChunk(arg);
  else if (cmd === "assemble") await cmdAssemble();
  else throw new Error("usage: long_render.mjs plan | chunk <index> | assemble");
} catch (e) {
  console.error("[neurotriage-long] FAILED:", e?.message || e);
  process.exit(1);
}
