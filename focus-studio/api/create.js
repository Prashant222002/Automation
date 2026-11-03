import { guard, llm, hasLLM, aiHtml, analyzeReference, validHtml, parseScript, parseJSON, E, PRESET_IDS } from "./_lib.js";
import { cleanSpec, submit, https } from "./_spec.js";

async function writeScript(spec) {
  const n = spec.format === "reel" ? 10 : 22, hi = spec.voice.lang !== "en";
  const t = await llm({ prefer: "groq", system: "You write tight, engaging voiceover scripts for short videos.",
    prompt: `Topic: ${spec.topic}\nWrite a ${spec.format === "reel" ? "30-45 second reel" : "3-5 minute video"} voiceover. ONE short sentence per line, at most ${n} lines, a strong hook first, a call-to-action last. Language: ${hi ? "Hindi in Devanagari script" : "English"}. Output only the lines.` });
  return t.replace(/^\s*[-*\d.)]+\s*/gm, "").trim();
}
function applyStyle(spec, st, b) {
  if (PRESET_IDS.includes(st.preset)) spec.preset = st.preset;
  if (!b.captions?.style && ["clean", "pop", "karaoke"].includes(st.captions)) spec.captions.style = st.captions;
  if (spec.music.source === "none" && ["calm", "upbeat", "dark", "epic"].includes(st.music_mood)) spec.music = { ...spec.music, source: "synth", style: st.music_mood };
  if (st.ending?.type === "none") spec.endcard.on = false;
  else if (st.ending?.text && !b.endcard?.text) spec.endcard.text = String(st.ending.text).slice(0, 60);
  if (st.ending?.type === "fade") spec.ending_hint = "fade";
}
async function addStock(spec, notes) {
  const key = E("PEXELS_API_KEY"); if (!key) { notes.push("Stock footage skip: PEXELS_API_KEY nahi hai (optional)."); return; }
  const lines = parseScript(spec.script).slice(0, 10); if (!lines.length) return;
  let kws = [];
  try { kws = parseJSON(await llm({ prefer: "groq", json: true, prompt: `For each line give a 1-3 word ENGLISH stock-video search keyword. Reply JSON {"k":[...${lines.length} strings]}.\n` + lines.map((l, i) => `${i + 1}. ${l.text}`).join("\n") }))?.k || []; } catch {}
  const out = []; const used = new Set();
  for (let i = 0; i < lines.length; i++) {
    const q = kws[i] || lines[i].text.split(/\s+/).sort((a, b) => b.length - a.length)[0];
    const r = await fetch(`https://api.pexels.com/videos/search?query=${encodeURIComponent(q)}&per_page=5&orientation=${spec.format === "reel" ? "portrait" : "landscape"}`, { headers: { Authorization: key } });
    if (!r.ok) continue; const j = await r.json();
    const v = (j.videos || []).find((x) => !used.has(x.id)) || j.videos?.[0]; if (!v) continue; used.add(v.id);
    const f = (v.video_files || []).filter((x) => x.link && x.file_type === "video/mp4" && x.width <= 1920).sort((a, b) => b.width - a.width)[0]; if (!f) continue;
    spec.clips.push({ url: f.link, name: `pexels-${q}` }); out[i] = spec.clips.length;
  }
  if (out.some(Boolean)) { spec.script = lines.map((l, i) => (out[i] ? `[clip:${out[i]}] ` : "") + l.text).join("\n"); notes.push(`Stock footage mili: ${spec.clips.length} clips (Pexels).`); }
}

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  if (!guard(req, res)) return;
  try {
    const b = req.body || {}, spec = cleanSpec(b), notes = [];
    if (spec.kind === "edit" && !spec.clips.length) return res.status(400).json({ error: "Kam se kam ek video upload karo ya link do." });
    if (spec.kind === "faceless" && !spec.script && !spec.voice.code) {
      if (spec.topic && hasLLM()) { spec.script = await writeScript(spec); notes.push("Script AI se banayi gayi."); }
      else return res.status(400).json({ error: "Script likho (ya topic do, AI key ke saath)." });
    }
    if (spec.kind === "faceless" && spec.voice.source === "code" && !spec.script) spec.script = (spec.voice.code.match(/^(?:hi|en):\s*(.+)$/gim) || []).map((x) => x.replace(/^(?:hi|en):\s*/i, "")).join("\n");
    let style = null; const ref = https(b.reference?.url);
    if (ref) { try { style = await analyzeReference(ref); notes.push("Reference style: " + (style.summary || "samajh liya")); applyStyle(spec, style, b); } catch (e) { notes.push("Reference skip: " + e.message); } }
    if (spec.kind === "faceless" && !spec.clips.length && b.stock) { try { await addStock(spec, notes); } catch (e) { notes.push("Stock skip: " + e.message); } }
    if (spec.mode === "ai") {
      if (!hasLLM()) return res.status(400).json({ error: "AI mode ke liye GEMINI_API_KEY ya GROQ_API_KEY chahiye. Preset ya Manual use karo (keys nahi lagti)." });
      spec.html = await aiHtml({ spec, instruction: String(b.prompt || "").slice(0, 2500), style });
    } else if (spec.mode === "manual" && spec.html) {
      const e = validHtml(spec.html); if (e) return res.status(400).json({ error: "Code me dikkat: " + e });
    } else spec.html = "";
    res.json({ id: await submit(spec), notes });
  } catch (e) { res.status(500).json({ error: e.message }); }
}
