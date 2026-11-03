import { guard, gh, REPO, release, hasLLM, aiHtml, validHtml } from "./_lib.js";
import { cleanSpec, submit } from "./_spec.js";
const get = async (rel, name) => { const a = rel.assets.find((x) => x.name === name); if (!a) throw new Error(name + " nahi mili (job expire?)"); return (await gh(`/repos/${REPO()}/releases/assets/${a.id}`, { headers: { Accept: "application/octet-stream" } })).text(); };
// body: {job, prompt?}  AI edit of the code | {job, html}  manual code | {job, patch:{preset,grade,hook,captions,endcard,music,title}} quick no-AI re-render
export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  if (!guard(req, res)) return;
  try {
    const b = req.body || {}, job = String(b.job || "").replace(/[^a-z0-9]/g, ""), rel = await release(job);
    if (!rel) return res.status(404).json({ error: "Job nahi mila (expire ho gaya?). Naya video banao." });
    const old = JSON.parse(await get(rel, "spec.json")); const spec = cleanSpec({ ...old, ...(b.patch || {}), html: "" });
    if (typeof b.html === "string" && b.html.trim()) { const e = validHtml(b.html); if (e) return res.status(400).json({ error: "Code me dikkat: " + e }); spec.html = b.html; spec.mode = "manual"; }
    else if (b.prompt) {
      if (!hasLLM()) return res.status(400).json({ error: "Prompt se edit ke liye GEMINI_API_KEY / GROQ_API_KEY chahiye. 'Quick' ya 'Code' option use karo." });
      spec.html = await aiHtml({ spec, instruction: String(b.prompt).slice(0, 2500), current: await get(rel, "composition.html") }); spec.mode = "ai";
    } else if (b.patch) { spec.html = ""; }
    else return res.status(400).json({ error: "Kuch change batao (prompt / code / quick)." });
    res.json({ id: await submit(spec) });
  } catch (e) { res.status(500).json({ error: e.message }); }
}
