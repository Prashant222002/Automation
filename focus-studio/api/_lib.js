// Shared helpers. Keys live ONLY in Vercel env vars: GEMINI_API_KEY, GROQ_API_KEY, GITHUB_TOKEN, GITHUB_REPO, APP_PIN
export const E = (k) => process.env[k] || "";
export const REPO = () => E("GITHUB_REPO");            // "owner/repo"
export const BRANCH = () => E("GITHUB_BRANCH") || "main";
export const WORKFLOW = "focus-render.yml";
export const PRESET_IDS = ["cinematic", "vlog", "news", "viral", "minimal", "neon", "documentary", "retro"];
export const GRADE_IDS = ["neutral","warm-daylight","clean-studio","skin-soft","food-pop","night-lift","muted-editorial","vintage-wash","mono-clean","mono-fade","soft-boost","bright-pop","deep-contrast","creator-camcorder","vhs-playback"];

export function guard(req, res, pin) {
  const want = E("APP_PIN");
  if (!want) { res.status(500).json({ error: "APP_PIN Vercel me set nahi hai (Settings > Environment Variables)." }); return false; }
  const got = pin ?? req.headers["x-pin"];
  if (got !== want) { res.status(401).json({ error: "PIN galat hai." }); return false; }
  return true;
}
export const keys = (prefix) => Object.keys(process.env).filter((k) => k === prefix || k.startsWith(prefix + "_")).sort().map((k) => process.env[k]).filter(Boolean);

export async function gh(path, opts = {}) {
  const r = await fetch(`https://api.github.com${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${E("GITHUB_TOKEN")}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "focus-studio", ...(opts.headers || {}) },
  });
  return r;
}
export async function release(job) {
  const r = await gh(`/repos/${REPO()}/releases/tags/job-${job}`);
  return r.ok ? r.json() : null;
}

// ---------- LLM (Gemini first for code/video, Groq first for quick text; each falls back to the other)
const GEMINI_MODEL = () => E("GEMINI_MODEL") || "gemini-2.5-flash";
const GROQ_MODEL = () => E("GROQ_MODEL") || "llama-3.3-70b-versatile";
async function geminiCall(body) {
  let last = "no GEMINI_API_KEY";
  for (const k of keys("GEMINI_API_KEY")) {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL()}:generateContent`, { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": k }, body: JSON.stringify(body) });
    if (r.ok) { const j = await r.json(); return (j.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join(""); }
    last = `gemini ${r.status}`; if (![429, 500, 503].includes(r.status) && r.status !== 403) break;
  }
  throw new Error(last);
}
async function groqCall(system, prompt, json) {
  let last = "no GROQ_API_KEY";
  for (const k of keys("GROQ_API_KEY")) {
    const r = await fetch("https://api.groq.com/openai/v1/chat/completions", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${k}` },
      body: JSON.stringify({ model: GROQ_MODEL(), temperature: 0.6, messages: [{ role: "system", content: system || "You are a helpful assistant." }, { role: "user", content: prompt }], ...(json ? { response_format: { type: "json_object" } } : {}) }) });
    if (r.ok) { const j = await r.json(); return j.choices?.[0]?.message?.content || ""; }
    last = `groq ${r.status}`; if (![429, 500, 503].includes(r.status)) break;
  }
  throw new Error(last);
}
export const hasLLM = () => keys("GEMINI_API_KEY").length + keys("GROQ_API_KEY").length > 0;
export async function llm({ system = "", prompt, json = false, prefer = "gemini" }) {
  const g = () => geminiCall({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: prompt }] }], generationConfig: { temperature: 0.6, ...(json ? { responseMimeType: "application/json" } : {}) } });
  const q = () => groqCall(system, prompt, json);
  const order = prefer === "groq" ? [q, g] : [g, q];
  let err;
  for (const f of order) { try { const t = await f(); if (t && t.trim()) return t; } catch (e) { err = e; } }
  throw new Error("AI keys kaam nahi kar rahi (" + (err?.message || "?") + "). Preset ya Manual mode use karo.");
}
export const parseJSON = (t) => { try { return JSON.parse(t.replace(/^```(?:json)?|```$/gim, "").trim()); } catch { const m = t.match(/[\[{][\s\S]*[\]}]/); if (m) { try { return JSON.parse(m[0]); } catch {} } return null; } };
export const stripFence = (t) => t.replace(/^\s*```(?:html)?\s*/i, "").replace(/\s*```\s*$/i, "").trim();

// ---------- HyperFrames code contract given to the AI
export const HF_RULES = `You write ONE self-contained HyperFrames composition: a single index.html that is rendered to MP4 by seeking a paused GSAP timeline.
HARD RULES:
- <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script> in <head>. html/body width+height = the canvas size, overflow hidden.
- Root: <div id="root" data-composition-id="main" data-start="0" data-duration="{{TOTAL}}" data-width="{{W}}" data-height="{{H}}"> (position:absolute; left:0; top:0; width/height = canvas).
- Every timed element has class="clip" plus data-start and data-duration (seconds). A clip shows over [start, start+duration).
- Use the timing tokens exactly as written, e.g. data-start="{{S2_START}}" data-duration="{{S2_DUR}}". They are replaced before rendering. Never invent numbers for scene timing.
- One timeline: const tl = gsap.timeline({paused:true}); ...tweens...; window.__timelines = window.__timelines || {}; window.__timelines["main"] = tl; (register at the very end). Tween times may use tokens too, e.g. {{S2_START}}.
- No Date.now(), no Math.random(), no fetch/network, no timers, no repeat:-1 (use finite repeats). Everything is a function of timeline time.
- Never tween display/visibility/autoAlpha on a .clip; animate a CHILD (or opacity). Do not put CSS transform on an element GSAP animates; use gsap.fromTo (never gsap.from).
- Video: <video class="clip" src="assets/FILE" muted playsinline data-start data-duration style="position:absolute;left:0;top:0;width:{{W}}px;height:{{H}}px;object-fit:cover"></video>. To zoom/move a video, wrap it in a NON-timed div and tween the wrapper. Always muted: audio is mixed separately. Do NOT add <audio>.
- Color grade footage with the attribute data-color-grading='{"preset":"<id>","intensity":1}' on the <video> (never CSS filters). Preset ids: ${GRADE_IDS.join(", ")}.
- Fonts that resolve by name: Inter, Montserrat, Outfit, Poppins, Oswald, Playfair Display, EB Garamond, Space Mono, Roboto, Lato. For Hindi/Devanagari text add @font-face{font-family:"FocusDev";src:local("Noto Sans Devanagari")} and use font-family:"<latin font>","FocusDev",sans-serif.
- Keep important text inside the central 80% (title-safe). Reels (portrait): keep the bottom 30% free for captions.
- Captions are generated automatically: put the comment <!--FOCUS_CAPTIONS--> as the LAST child inside #root and put /*FOCUS_CAPTIONS_JS*/ on its own line inside the script just before the window.__timelines line. Do not draw your own captions.
- If an end card is requested, show it from {{ENDCARD_START}} until {{TOTAL}} with an opaque full-frame background.
Return ONLY the complete HTML document. No markdown fences, no explanation.`;

export function parseScript(text = "") {
  const out = [];
  for (let ln of String(text).split(/\r?\n/)) {
    ln = ln.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim();
    if (!ln || ln.startsWith("#")) continue;
    const m = ln.match(/\[clip:\s*(\d+)\]/i); ln = ln.replace(/\[clip:\s*\d+\]/gi, "").trim();
    if (ln) out.push({ text: ln, clip: m ? +m[1] : null });
  }
  return out;
}
export function scenePlan(spec) {
  if (spec.kind !== "faceless" && spec.clips.length) return spec.clips.map((c, k) => ({ i: k + 1, file: `clip${k + 1}.mp4`, text: "" }));
  return parseScript(spec.script).map((l, k) => ({ i: k + 1, file: spec.clips.length ? `s${k + 1}.mp4` : null, text: l.text }));
}
export function validHtml(h) {
  if (!/data-composition-id\s*=\s*["']main["']/.test(h)) return "root me data-composition-id=\"main\" nahi mila";
  if (!/__timelines/.test(h)) return "window.__timelines[\"main\"] register nahi hua";
  if (/repeat\s*:\s*-1/.test(h) || /Date\.now\(|Math\.random\(/.test(h)) return "Date.now / Math.random / repeat:-1 allowed nahi";
  return "";
}
export async function aiHtml({ spec, instruction, style, current }) {
  const plan = scenePlan(spec); const reel = spec.format === "reel"; const W = reel ? 1080 : 1920, H = reel ? 1920 : 1080;
  const info = `Canvas ${W}x${H} (${reel ? "vertical reel" : "horizontal long video"}), 30fps. Kind: ${spec.kind}. Preset hint: ${spec.preset}. Hook text: "${spec.hook || ""}". Title: "${spec.title || ""}". End card: ${spec.endcard.on ? `yes, text "${spec.endcard.text}" sub "${spec.endcard.sub}"` : "no"}.
Scenes (use these exact tokens for each):\n${plan.map((s) => `- scene ${s.i}: tokens {{S${s.i}_START}} {{S${s.i}_DUR}}; video file ${s.file ? "assets/" + s.file : "NONE (make an animated text/graphics scene)"}; text: ${JSON.stringify(s.text)}`).join("\n") || "- (no scenes)"}
${style ? "Reference style to imitate (do not copy content): " + JSON.stringify(style) : ""}`;
  let prompt = current ? `${info}\n\nCURRENT COMPOSITION:\n${current}\n\nEDIT REQUEST (apply it, keep everything else, keep tokens/markers/rules): ${instruction}` : `${info}\n\nVIDEO BRIEF: ${instruction || "Professional, polished edit."}`;
  let html = "", err = "";
  for (let n = 0; n < 2; n++) {
    html = stripFence(await llm({ system: HF_RULES, prompt: prompt + (err ? `\n\nYour previous answer was rejected: ${err}. Fix it.` : ""), prefer: "gemini" }));
    err = validHtml(html); if (!err) return html;
  }
  throw new Error("AI ne valid HyperFrames code nahi diya (" + err + "). Dobara try karo ya Preset/Manual use karo.");
}

// ---------- reference video analysis (Gemini sees the video)
export async function analyzeReference(url) {
  const ks = keys("GEMINI_API_KEY"); if (!ks.length) throw new Error("Reference analysis ke liye GEMINI_API_KEY chahiye.");
  const key = ks[0]; let part;
  if (/youtu\.?be/.test(url)) part = { fileData: { fileUri: url } };
  else {
    const vr = await fetch(url); if (!vr.ok) throw new Error("reference video download nahi hui");
    const buf = Buffer.from(await vr.arrayBuffer()); if (buf.length > 60e6) throw new Error("reference video 60MB se chhoti rakho (ya 1-2 min ka clip).");
    const mime = vr.headers.get("content-type") || "video/mp4";
    if (buf.length <= 18e6) part = { inlineData: { mimeType: mime, data: buf.toString("base64") } };
    else {
      const s = await fetch(`https://generativelanguage.googleapis.com/upload/v1beta/files?key=${key}`, { method: "POST", headers: { "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": String(buf.length), "X-Goog-Upload-Header-Content-Type": mime, "Content-Type": "application/json" }, body: JSON.stringify({ file: { display_name: "ref" } }) });
      const up = s.headers.get("x-goog-upload-url"); if (!up) throw new Error("Gemini file upload start fail");
      const f = await (await fetch(up, { method: "POST", headers: { "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize" }, body: buf })).json();
      let file = f.file; for (let i = 0; i < 25 && file?.state !== "ACTIVE"; i++) { await new Promise((r) => setTimeout(r, 2000)); file = await (await fetch(`https://generativelanguage.googleapis.com/v1beta/${file.name}?key=${key}`)).json(); }
      if (file?.state !== "ACTIVE") throw new Error("Gemini video process nahi kar paya (time out)");
      part = { fileData: { fileUri: file.uri, mimeType: mime } };
    }
  }
  const ask = `Analyse the EDITING STYLE of this video (not its subject). Return JSON only: {"pace":"fast|medium|slow","avg_shot_sec":number,"transitions":"hard|fade|zoom|whip","grade":"warm|cool|mono|vivid|muted|retro|neutral","captions":"none|clean|pop|karaoke","music_mood":"calm|upbeat|dark|epic|none","hook":"how the first 2 seconds work","ending":{"type":"card|fade|logo|none","text":"text shown at the end if any","seconds":number,"description":"what the ending looks like"},"palette":["#hex","#hex"],"preset":"one of ${PRESET_IDS.join("|")} (closest match)","summary":"2 lines in Hinglish"}`;
  const t = await geminiCall({ contents: [{ role: "user", parts: [part, { text: ask }] }], generationConfig: { responseMimeType: "application/json" } });
  const j = parseJSON(t); if (!j) throw new Error("reference analysis ka JSON samajh nahi aaya");
  return j;
}
