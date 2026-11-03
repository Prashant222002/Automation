import { guard, gh, REPO, WORKFLOW, release } from "./_lib.js";
export default async function handler(req, res) {
  if (!guard(req, res)) return;
  const job = String(req.query.job || "").replace(/[^a-z0-9]/g, "");
  try {
    const wfs = [WORKFLOW, process.env.LONG_WORKFLOW || "neurotriage-long.yml"];
    const runs = [];
    for (const w of wfs) {
      const rr = await gh(`/repos/${REPO()}/actions/workflows/${w}/runs?per_page=40`);
      if (rr.ok) runs.push(...((await rr.json()).workflow_runs || []));
    }
    if (!runs.length) return res.status(502).json({ error: "GitHub se status nahi mila" });
    const run = runs.find((x) => (x.display_title || x.name || "").includes(`render ${job}`));
    if (!run) return res.json({ state: "queued", pct: 3, label: "Queue me…" });
    const jr = await (await gh(`/repos/${REPO()}/actions/runs/${run.id}/jobs`)).json();
    const steps = jr.jobs?.[0]?.steps || [], total = steps.length || 1;
    const done = steps.filter((x) => x.status === "completed").length, cur = steps.find((x) => x.status === "in_progress");
    const out = { run: run.id, label: cur?.name || "Shuru ho raha hai…", stepPct: Math.round((done / total) * 100), nextPct: Math.round(((done + 1) / total) * 100) };
    if (run.status !== "completed") return res.json({ state: "running", pct: Math.max(5, out.stepPct), ...out });
    if (run.conclusion === "success") { const rel = await release(job); return res.json({ state: "done", pct: 100, assets: (rel?.assets || []).map((a) => a.name), label: "Ready" }); }
    const bad = steps.find((x) => x.conclusion === "failure");
    res.json({ state: "failed", pct: out.stepPct, label: bad ? `Fail: ${bad.name}` : "Fail", url: run.html_url });
  } catch (e) { res.status(500).json({ error: e.message }); }
}
