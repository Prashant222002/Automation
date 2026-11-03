import { guard, E, keys } from "./_lib.js";
export default async function handler(req, res) {
  if (!guard(req, res)) return;
  res.json({ ok: true, gemini: keys("GEMINI_API_KEY").length, groq: keys("GROQ_API_KEY").length, github: !!E("GITHUB_TOKEN") && !!E("GITHUB_REPO"), blob: !!E("BLOB_READ_WRITE_TOKEN"), pexels: !!E("PEXELS_API_KEY") });
}
