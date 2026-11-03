import { guard, gh, REPO, release } from "./_lib.js";
// ?job=&name=final.mp4&mode=url  -> {url} (short-lived signed link, browser downloads straight from GitHub storage)
// ?job=&name=thumb1.jpg           -> bytes (small files, same-origin so canvas can use them)
export default async function handler(req, res) {
  if (!guard(req, res)) return;
  const job = String(req.query.job || "").replace(/[^a-z0-9]/g, ""), name = String(req.query.name || "");
  if (!/^[\w.-]+$/.test(name)) return res.status(400).json({ error: "bad name" });
  try {
    const rel = await release(job); const a = rel?.assets?.find((x) => x.name === name);
    if (!a) return res.status(404).json({ error: "File nahi mili (expire ho gayi ho sakti hai)." });
    const api = `/repos/${REPO()}/releases/assets/${a.id}`;
    if (req.query.mode === "url") {
      const r = await gh(api, { headers: { Accept: "application/octet-stream" }, redirect: "manual" });
      const loc = r.headers.get("location"); if (!loc) return res.status(502).json({ error: "download link nahi mila" });
      return res.json({ url: loc });
    }
    if (a.size > 25e6) return res.status(413).json({ error: "badi file: mode=url use karo" });
    const r = await gh(api, { headers: { Accept: "application/octet-stream" } });
    res.setHeader("Content-Type", a.content_type || "application/octet-stream"); res.setHeader("Cache-Control", "private, max-age=300");
    res.send(Buffer.from(await r.arrayBuffer()));
  } catch (e) { res.status(500).json({ error: e.message }); }
}
