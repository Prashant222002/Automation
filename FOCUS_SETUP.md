# NeuroTriage Advance Engine — setup (10 minute, ek baar)

## Kya hai
GitHub = render machine (HyperFrames + ffmpeg). Vercel = glassy PWA control panel. Video seedha Vercel app se download hoti hai.

## Step 1 — files sahi jagah
HyperFrames folder ke andar `setup_focus.py` rakho aur chalao:
    python setup_focus.py
Ye apne aap banata hai: `focus/`, `focus-studio/`, `.github/workflows/focus-render.yml`.

## Step 2 — GitHub
Poora folder (HyperFrames as-it-is + naye folders) apni GitHub repo me push karo.
Repo **private** rakho (aapki videos/links safe). Settings -> Actions -> General -> "Allow all actions" on.
GitHub token banao: Settings -> Developer settings -> Fine-grained tokens -> sirf is repo ke liye:
**Actions: Read and write**, **Contents: Read and write**, **Metadata: Read**.

## Step 3 — Vercel
1. Vercel -> Add New Project -> apni repo import karo.
2. **Root Directory = `focus-studio`** (zaroori).
3. Deploy hone do, phir Storage tab -> **Create Blob store** -> project se connect (BLOB_READ_WRITE_TOKEN khud aa jata hai). Redeploy.
4. Settings -> Environment Variables:
| Name | Value | Zaroori? |
|---|---|---|
| `GITHUB_TOKEN` | upar wala token | haan |
| `GITHUB_REPO` | `username/repo-name` | haan |
| `APP_PIN` | koi bhi PIN (app khulne ka password) | haan |
| `GEMINI_API_KEY` | Gemini key | sirf AI mode / reference / metadata |
| `GROQ_API_KEY` | Groq key | sirf AI mode / script / metadata |
| `GITHUB_BRANCH` | `main` (agar alag ho) | nahi |
| `PEXELS_API_KEY` | free stock video | nahi |
Preset aur Manual mode me Gemini/Groq ki zaroorat **nahi**.

## Step 4 — phone me
Vercel URL kholo -> Settings tab me PIN daalo -> "Save + Test" -> Install (Android) / Share -> Add to Home Screen (iPhone).

## Manual mode ke tokens (HyperFrames code me)
`{{TOTAL}} {{W}} {{H}} {{S1_START}} {{S1_DUR}} … {{ENDCARD_START}} {{VOICE_DUR}}`
Captions: `<!--FOCUS_CAPTIONS-->` (root ke aakhir me) aur `/*FOCUS_CAPTIONS_JS*/` (script me, `window.__timelines` se pehle).
Files: edit mode `assets/clip1.mp4…`, faceless (clips ke saath) `assets/s1.mp4…`, voice `assets/voice.wav` (sound alag mix hoti hai, `<audio>` mat daalo).

## Audio code (manual voice)
    voice: hf_alpha
    hi: नमस्ते दोस्तों
    sfx: whoosh
    pause: 0.4
    en: Welcome back
    music: upbeat

## Limits (sach)
- Videos GitHub release me 7 din rehti hain (`KEEP_DAYS`), phir auto delete.
- Private repo me Actions minutes limited (free plan 2000/month). Public repo me unlimited, par tab output public hota hai.
- Built-in music basic ambient hai; behtar music ke liye apna upload karo.
- Instagram/YouTube auto-post nahi hai; title/caption/tags copy karke daalte ho.

## v2 — Editor aur dashboard upgrade
- **Editor**: dashboard header me "✏️ Editor" button, ya seedha `/editor.html`. Yahan:
  - Template chuno (Reel, 3D rotating object, Counter), code likho, preview turant update hoga.
  - Timeline slider se kisi bhi second par ruk kar check karo. Play/Pause bhi hai.
  - "Check" red errors dikhata hai (jaise missing `data-composition-id`, `Math.random`, unknown token).
  - Script likho, "Render video" dabao. Ye same GitHub pipeline use karta hai (manual mode), progress bar aur download wahin milega.
- **Draft**: editor code browser me save hota hai (Ctrl/⌘+S). Ye sirf tumhare browser me rehta hai.
- **Per-run folder**: har render ki GitHub release (`job-<id>`) me ab `manifest.json` bhi hota hai. Isme title, duration, preset, format, warnings aur saari files ki list hoti hai.
- **Dashboard**: naya dark theme, desktop par 2-column layout, shimmer progress bar. Saare features wahi hain.

## Abhi nahi hai (sach)
- Level 3 (realistic 3D organs/blood flow): HyperFrames me Three.js scene chal sakti hai, par realistic anatomy ke liye licensed 3D model (glTF) alag se chahiye.
- Level 4 (consistent cartoon characters + lip-sync): ye abhi pura automatic nahi hai. Lip-sync ke liye phoneme tool (jaise Rhubarb) aur character art alag se chahiye.

## Long video mode (1-2 hr aur usse bhi)
- Editor ya Create me format **16:9 Long** chuno. Script ki limit 200,000 characters hai.
- Long job `neurotriage-long.yml` workflow par jaata hai. Ye video ko chunks (default 5 min) me banata hai, har chunk alag GitHub job me chalta hai, phir HyperFrames ke `assembleV2` se sab jodta hai.
- Chunk aur assemble ke liye `LONG_WORKFLOW` env var optional hai (default `neurotriage-long.yml`).
- Final file GitHub ki 2 GB limit ke liye bade hone par `part-01.mp4`, `part-02.mp4` ... me split hoti hai (har part ~20 min).
- Long render ka time aur Actions minutes bahut zyada lagte hain. Private repo ka free plan (2000 min/month) 1-2 hr video ke liye kaafi nahi hai. Pehle 5-10 min ka test chalao, us se timing nikalo, phir `NT_CHUNK_FRAMES` tune karo.
- Abhi dashboard me long job ke parts ki list nahi dikhti. Release page par sab files milti hain.
