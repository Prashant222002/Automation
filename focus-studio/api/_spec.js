import { put } from "@vercel/blob";
import { gh, REPO, BRANCH, WORKFLOW, PRESET_IDS, GRADE_IDS } from "./_lib.js";
const s = (v, n = 200) => String(v ?? "").slice(0, n);
const num = (v, lo, hi, d) => { const x = Number(v); return Number.isFinite(x) ? Math.min(hi, Math.max(lo, x)) : d; };
export const https = (u) => (typeof u === "string" && u.startsWith("https://") ? u.slice(0, 2000) : "");
const pick = (v, list, d) => (list.includes(v) ? v : d);

export function cleanSpec(b = {}) {
  const v = b.voice || {}, m = b.music || {}, c = b.captions || {}, e = b.endcard || {}, g = b.grade || {};
  return {
    kind: pick(b.kind, ["edit", "faceless"], "edit"),
    format: b.format === "long" ? "long" : "reel",
    mode: pick(b.mode, ["preset", "ai", "manual"], "preset"),
    preset: pick(b.preset, PRESET_IDS, "viral"),
    grade: GRADE_IDS.includes(g.preset) ? { preset: g.preset, intensity: num(g.intensity, 0, 1, 1) } : null,
    title: s(b.title, 120), hook: s(b.hook, 90), script: s(b.script, b.format === "long" ? 200000 : 8000), topic: s(b.topic, 300),
    clips: (Array.isArray(b.clips) ? b.clips : []).slice(0, 12).map((x) => ({ url: https(x?.url), name: s(x?.name, 60),
      trim: Array.isArray(x?.trim) && x.trim.length === 2 ? x.trim.map(Number) : undefined })).filter((x) => x.url),
    voice: { source: pick(v.source, ["none", "generate", "upload", "code"], "none"), lang: v.lang === "en" ? "en" : "hi", voice: s(v.voice, 30),
      speed: num(v.speed, 0.6, 1.5, 1), cleanup: v.cleanup !== false, code: s(v.code, 4000), url: https(v.url) },
    music: { source: pick(m.source, ["none", "synth", "upload"], "none"), style: pick(m.style, ["calm", "upbeat", "dark", "epic"], "calm"), volume: num(m.volume, 0.02, 0.6, 0.16), url: https(m.url) },
    captions: { on: c.on !== false, style: pick(c.style, ["clean", "pop", "karaoke"], "") },
    endcard: { on: e.on !== false, text: s(e.text, 60) || "Like • Share • Follow", sub: s(e.sub, 80), button: s(e.button, 20) || "FOLLOW" },
    html: s(b.html, 250000),
  };
}

export async function submit(spec) {
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  spec.id = id; spec.created = new Date().toISOString();
  const wf = spec.format === "long" ? (process.env.LONG_WORKFLOW || "neurotriage-long.yml") : WORKFLOW;
  const { url } = await put(`focus/${id}/spec.json`, JSON.stringify(spec), { access: "public", contentType: "application/json", addRandomSuffix: true });
  const r = await gh(`/repos/${REPO()}/actions/workflows/${wf}/dispatches`, { method: "POST", body: JSON.stringify({ ref: BRANCH(), inputs: { job: id, spec: url } }) });
  if (r.status !== 204) throw new Error(`GitHub workflow start nahi hua (${r.status}). GITHUB_TOKEN / GITHUB_REPO check karo. ${(await r.text()).slice(0, 160)}`);
  return id;
}
