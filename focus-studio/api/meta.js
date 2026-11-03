import { guard, gh, REPO, release, llm, hasLLM, parseJSON } from "./_lib.js";
const tagsFrom = (t) => { const c = {}; (t.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || []).forEach((w) => (c[w] = (c[w] || 0) + 1)); return Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 12).map((x) => x[0]); };
export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();
  if (!guard(req, res)) return;
  try {
    const job = String(req.body?.job || "").replace(/[^a-z0-9]/g, ""), rel = await release(job);
    const a = rel?.assets?.find((x) => x.name === "meta_src.json"); if (!a) return res.status(404).json({ error: "meta source nahi mila" });
    const src = await (await gh(`/repos/${REPO()}/releases/assets/${a.id}`, { headers: { Accept: "application/octet-stream" } })).json();
    const text = (src.transcript || src.script || "").slice(0, 6000);
    if (hasLLM() && text) {
      const j = parseJSON(await llm({ prefer: "groq", json: true, system: "You are a social media growth expert for YouTube and Instagram.",
        prompt: `Video: ${src.format === "reel" ? "vertical short" : "long horizontal"}, ${src.duration}s. Working title: "${src.title}". Content/transcript:\n${text}\n\nWrite in the SAME language/style as the content (Hinglish stays Hinglish). Return JSON: {"youtube":{"title":"max 70 chars, curiosity + keyword","description":"3-5 lines + CTA + 3 hashtags","tags":["10-15 tags"]},"shorts_title":"max 60 chars","instagram":{"caption":"hook line + 2-3 short lines + CTA","hashtags":["15-20 hashtags without #"]}}` }));
      if (j) return res.json({ ...j, ai: true });
    }
    const tg = tagsFrom(text + " " + (src.title || "")), t = src.title || text.split(/[.!?\n]/)[0].slice(0, 70) || "My video";
    res.json({ ai: false, youtube: { title: t.slice(0, 70), description: `${text.slice(0, 200)}\n\nLike, share & subscribe!\n${tg.slice(0, 3).map((x) => "#" + x).join(" ")}`, tags: tg }, shorts_title: t.slice(0, 60),
      instagram: { caption: `${t}\n\nFollow for more!`, hashtags: tg.slice(0, 15) } });
  } catch (e) { res.status(500).json({ error: e.message }); }
}
