#!/usr/bin/env python3
"""NeuroTriage Advance Engine render pipeline (runs inside GitHub Actions).
Stages: fetch -> voice -> captions -> compose -> render -> finish.   No API keys are used here:
voice = HyperFrames tts (Kokoro, local) or edge-tts, captions = hyperframes transcribe (whisper, local),
grading = HyperFrames built-in color-grading presets, audio = ffmpeg."""
import json, os, re, sys, shutil, subprocess, urllib.request, pathlib, html as H, math, glob
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from presets import PRESETS, DEFAULT, VOICES, EDGE

WORK = pathlib.Path(os.environ.get("FOCUS_WORK", "work")).resolve()
PROJ, TMP, OUT = WORK / "proj", WORK / "tmp", WORK / "out"
AS = PROJ / "assets"
HFV = os.environ.get("HF_VERSION", "0.8.224")
HF = ["npx", "-y", f"hyperframes@{HFV}"]
DRY = os.environ.get("FOCUS_DRY") == "1"
IMG = (".jpg", ".jpeg", ".png", ".webp")

def log(*a): print("[focus]", *a, flush=True)
def sh(cmd, check=True, cwd=None, cap=False):
    log("$", " ".join(str(c) for c in cmd)[:220])
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, check=False, stdin=subprocess.DEVNULL,
                       capture_output=cap, text=True)
    if check and r.returncode:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))[:160]}\n{(r.stderr or '')[-800:]}")
    return r
def jl(p): return json.loads(pathlib.Path(p).read_text("utf-8"))
def jd(p, o): pathlib.Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=1), "utf-8")
def dur(p):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], cap=True)
    return float(r.stdout.strip() or 0)
def has_audio(p):
    r = sh(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", p], cap=True)
    return bool(r.stdout.strip())
def ff(*a): sh(["ffmpeg", "-y", "-loglevel", "error", *a])
def f3(x): return f"{x:.3f}"
def esc(s): return H.escape(str(s), quote=True)

def download(url, dest):
    if not url.startswith("https://"):
        if DRY and pathlib.Path(url).exists(): shutil.copy(url, dest); return
        raise RuntimeError("only https links are allowed")
    req = urllib.request.Request(url, headers={"User-Agent": "focus-studio/1"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f: shutil.copyfileobj(r, f)

def S(): return jl(WORK / "spec.json")
def ST(): return jl(WORK / "state.json")
def save(st): jd(WORK / "state.json", st)
def warn(st, msg): log("WARNING:", msg); st.setdefault("warnings", []).append(msg)

# ---------------------------------------------------------------- fetch
def norm_clip(raw, dest, W, H_, c):
    vf = f"scale={W}:{H_}:force_original_aspect_ratio=increase,crop={W}:{H_},fps=30,setsar=1"
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]
    if str(raw).lower().endswith(IMG):
        ff("-loop", "1", "-t", str(c.get("dur") or 4), "-i", raw, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-shortest", *enc, dest); return
    trim = []
    t = c.get("trim")
    if t and len(t) == 2 and t[1] > t[0]: trim = ["-ss", str(t[0]), "-to", str(t[1])]
    if has_audio(raw): ff(*trim, "-i", raw, "-t", "900", "-vf", vf, *enc, dest)
    else: ff(*trim, "-i", raw, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "900", "-vf", vf, "-map", "0:v", "-map", "1:a", "-shortest", *enc, dest)

def stage_fetch():
    for d in (WORK, TMP, OUT): d.mkdir(parents=True, exist_ok=True)
    url = os.environ.get("SPEC_URL", "")
    download(url, WORK / "spec.json"); sp = S()
    reel = sp.get("format", "reel") == "reel"
    W, H_ = (1080, 1920) if reel else (1920, 1080)
    if not DRY:
        sh(HF + ["init", "proj", "--example", "blank"], cwd=WORK, check=False)
    PROJ.mkdir(exist_ok=True); AS.mkdir(exist_ok=True)
    clips = []
    for i, c in enumerate(sp.get("clips", []), 1):
        ext = pathlib.Path(c["url"].split("?")[0]).suffix.lower() or ".mp4"
        raw = TMP / f"raw{i}{ext}"; download(c["url"], raw)
        dest = AS / f"clip{i}.mp4"; norm_clip(str(raw), str(dest), W, H_, c)
        clips.append({"i": i, "name": c.get("name", ""), "dur": dur(str(dest))})
    v = sp.get("voice", {}) or {}
    if v.get("url"): download(v["url"], TMP / "voice_in")
    m = sp.get("music", {}) or {}
    if m.get("url"): download(m["url"], TMP / "music_in")
    save({"W": W, "H": H_, "reel": reel, "clips": clips, "warnings": []})

# ---------------------------------------------------------------- voice
CLEAN = "highpass=f=70,lowpass=f=15000,afftdn=nr=12:nf=-30,acompressor=threshold=-18dB:ratio=3:attack=5:release=80,loudnorm=I=-16:TP=-1.5:LRA=11"
def tts(text, lang, voice, speed, out):
    text = text.strip().lstrip("-").strip()
    if DRY or os.environ.get("FOCUS_FAKE_TTS"):
        ff("-f", "lavfi", "-i", f"sine=f=220:d={max(0.8, len(text) * 0.06):.2f}", "-ar", "24000", out); return
    try:
        sh(HF + ["tts", text, "--voice", voice, "--speed", str(speed), "--output", out], cwd=WORK)
        if not pathlib.Path(out).exists() or pathlib.Path(out).stat().st_size < 1000: raise RuntimeError("empty tts file")
    except Exception as e:
        log("hyperframes tts failed, trying edge-tts:", str(e)[:200])
        mp3 = str(out) + ".mp3"
        sh(["edge-tts", "--voice", EDGE.get(lang, EDGE["en"]), "--text", text, "--write-media", mp3])
        ff("-i", mp3, "-ar", "24000", out)

def synth_sfx(name, out):
    ex = {"whoosh": "anoisesrc=d=0.7:c=pink:r=48000,lowpass=f=3000,afade=t=in:d=0.3,afade=t=out:st=0.35:d=0.35,volume=0.7",
          "pop": "aevalsrc='0.8*sin(2*PI*(500+900*t)*t)*exp(-30*t)':d=0.15:s=48000",
          "click": "aevalsrc='0.7*sin(2*PI*2400*t)*exp(-90*t)':d=0.08:s=48000",
          "ding": "aevalsrc='(0.6*sin(2*PI*1320*t)+0.3*sin(2*PI*1980*t))*exp(-5*t)':d=1.2:s=48000",
          "boom": "aevalsrc='0.9*sin(2*PI*(70-35*t)*t)*exp(-3*t)':d=1.4:s=48000",
          "riser": "aevalsrc='0.5*sin(2*PI*(200+500*t)*t)*t/1.6':d=1.6:s=48000"}
    ff("-f", "lavfi", "-i", ex.get(name, ex["pop"]), "-ar", "48000", out)

def parse_dsl(code):
    """key: value lines.  hi: text | en: text | pause: 0.5 | sfx: whoosh | voice: hf_alpha | speed: 1.0 | music: calm"""
    ev, music = [], None
    voice, speed = None, 1.0
    for ln in code.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ":" not in ln: continue
        k, v = ln.split(":", 1); k, v = k.strip().lower(), v.strip()
        if k in ("hi", "en"): ev.append(("say", k, v, voice, speed))
        elif k == "pause":
            try: ev.append(("pause", float(v)))
            except ValueError: pass
        elif k == "sfx": ev.append(("sfx", v.lower()))
        elif k == "voice": voice = v
        elif k == "speed":
            try: speed = float(v)
            except ValueError: pass
        elif k == "music": music = v.lower()
    return ev, music

def parse_script(text):
    lines = []
    for ln in (text or "").splitlines():
        ln = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip()
        if not ln or ln.startswith("#"): continue
        m = re.search(r"\[clip:\s*(\d+)\]", ln, re.I); clip = int(m.group(1)) if m else None
        ln = re.sub(r"\[clip:\s*\d+\]", "", ln, flags=re.I).strip()
        if ln: lines.append({"text": ln, "clip": clip})
    return lines

def stage_voice():
    sp, st = S(), ST(); v = sp.get("voice", {}) or {}
    src = v.get("source") or ("generate" if sp.get("kind") == "faceless" else "none")
    lang = v.get("lang", "hi"); speed = float(v.get("speed") or 1.0)
    vname = v.get("voice") or VOICES.get(lang, VOICES["en"])[0]
    st["voice"] = False; scenes = []
    dsl_music = None
    if src in ("generate", "code"):
        if src == "code":
            ev, dsl_music = parse_dsl(v.get("code", ""))
            items = ev
        else:
            lines = parse_script(sp.get("script") or v.get("text") or "")
            items = [("say", lang, ln["text"], None, speed, ln["clip"]) for ln in lines]
        if not items: warn(st, "voice requested but there is no script text"); save(st); return
        t, segs, gap, k = 0.2, [], 0.35, 0
        for it in items:
            if it[0] == "pause": t += it[1]; continue
            if it[0] == "sfx":
                p = TMP / f"sfx{k}.wav"; synth_sfx(it[1], str(p)); segs.append((t, str(p))); k += 1; continue
            _, lg, text, vn, spd = it[:5]; clip = it[5] if len(it) > 5 else None
            p = TMP / f"seg{k}.wav"; k += 1
            tts(text, lg, vn or (vname if lg == lang else VOICES[lg][0]), spd, str(p))
            d = dur(str(p)); segs.append((t, str(p)))
            scenes.append({"text": text, "clip": clip, "speech_start": t, "speech_dur": d})
            t += d + gap
        total = t
        ins, fl = [], []
        for n, (ts, p) in enumerate(segs):
            ins += ["-i", p]; ms = int(ts * 1000); fl.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=mono,adelay={ms}[a{n}]")
        mix = "".join(f"[a{n}]" for n in range(len(segs)))
        fg = ";".join(fl) + f";{mix}amix=inputs={len(segs)}:normalize=0:duration=longest[o]"
        ff(*ins, "-filter_complex", fg, "-map", "[o]", "-ar", "48000", str(TMP / "voice_raw.wav"))
    elif src == "upload" and (TMP / "voice_in").exists():
        ff("-i", str(TMP / "voice_in"), "-vn", "-ar", "48000", "-ac", "1", str(TMP / "voice_raw.wav"))
        total = dur(str(TMP / "voice_raw.wav"))
        lines = parse_script(sp.get("script") or "")
        n = sum(len(l["text"]) for l in lines) or 1; t = 0.0
        for l in lines:
            d = total * len(l["text"]) / n
            scenes.append({"text": l["text"], "clip": l["clip"], "speech_start": t, "speech_dur": d}); t += d
    else:
        save(st); return
    vf = CLEAN if v.get("cleanup", True) else "loudnorm=I=-16:TP=-1.5:LRA=11"
    ff("-i", str(TMP / "voice_raw.wav"), "-af", vf, "-ar", "48000", "-ac", "1", str(AS / "voice.wav"))
    st["voice"] = True; st["voice_dur"] = dur(str(AS / "voice.wav")); st["vscenes"] = scenes
    if dsl_music and not (sp.get("music") or {}).get("style"): st["dsl_music"] = dsl_music
    save(st)

# ---------------------------------------------------------------- captions
def norm_words(obj):
    out = []
    def walk(o):
        if isinstance(o, list):
            for x in o: walk(x)
        elif isinstance(o, dict):
            t = o.get("text", o.get("word"))
            if isinstance(t, str) and "start" in o and "end" in o and not o.get("words"):
                try: out.append({"t": t.strip(), "s": float(o["start"]), "e": float(o["end"])})
                except (TypeError, ValueError): pass
            for k in ("words", "segments", "transcription", "results"):
                if k in o: walk(o[k])
    walk(obj)
    return [w for w in out if w["t"] and not re.fullmatch(r"[♪\W_]*", w["t"]) and w["e"] > w["s"]]

def transcribe(path, lang):
    d = TMP / "tr"; shutil.rmtree(d, ignore_errors=True); d.mkdir()
    model = "small.en" if lang == "en" else "small"
    cmd = HF + ["transcribe", str(path), "--model", model] + (["--language", lang] if lang in ("hi", "en") else []) + ["--json"]
    r = sh(cmd, cwd=d, check=False, cap=True)
    cands = []
    try: cands.append(json.loads(r.stdout))
    except Exception: pass
    for p in sorted(glob.glob(str(d / "**" / "*.json"), recursive=True), key=os.path.getmtime, reverse=True):
        try: cands.append(json.loads(pathlib.Path(p).read_text("utf-8")))
        except Exception: pass
    for c in cands:
        w = norm_words(c)
        if w: return w
    return []

def stage_captions():
    sp, st = S(), ST(); cp = sp.get("captions", {}) or {}
    st["words"] = []
    if cp.get("on", True):
        lang = (sp.get("voice") or {}).get("lang") or sp.get("lang") or "auto"
        if st.get("voice") and st.get("vscenes"):
            for sc in st["vscenes"]:                      # words timed by character share inside each spoken line
                toks = sc["text"].split(); n = sum(len(x) for x in toks) or 1; t = sc["speech_start"]
                for x in toks:
                    d = sc["speech_dur"] * len(x) / n; st["words"].append({"t": x, "s": t, "e": t + d}); t += d
        elif st.get("voice") and not DRY:
            st["words"] = transcribe(AS / "voice.wav", lang)
        elif st["clips"] and sp.get("kind") != "faceless" and not DRY:
            ins = []
            for c in st["clips"]: ins += ["-i", str(AS / f"clip{c['i']}.mp4")]
            n = len(st["clips"])
            fg = "".join(f"[{k}:a]" for k in range(n)) + f"concat=n={n}:v=0:a=1[o]"
            ff(*ins, "-filter_complex", fg, "-map", "[o]", "-ar", "16000", "-ac", "1", str(TMP / "orig.wav"))
            st["words"] = transcribe(TMP / "orig.wav", lang)
        if not st["words"] and cp.get("on", True) and not DRY: warn(st, "captions: no words found (silent video or transcription failed)")
    save(st)

# ---------------------------------------------------------------- compose
def seg_video(src_clip, dst, d, offset):
    ff("-stream_loop", "-1", "-ss", f3(offset), "-i", str(AS / f"clip{src_clip}.mp4"), "-t", f3(d), "-an",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(dst))

def build_scenes(sp, st):
    clips = st["clips"]; scenes = []
    if sp.get("kind") != "faceless" and clips:                # raw / reference edit: one scene per clip
        t = 0.0
        for c in clips:
            scenes.append({"i": c["i"], "start": t, "dur": c["dur"], "text": "", "video": f"clip{c['i']}.mp4"}); t += c["dur"]
    else:                                                     # faceless: one scene per script line
        vs = st.get("vscenes") or [{"text": l["text"], "clip": l["clip"], "speech_start": None, "speech_dur": 0} for l in parse_script(sp.get("script", ""))]
        t, offs, rr = 0.0, {}, 0
        for k, v in enumerate(vs, 1):
            d = (v["speech_dur"] + 0.35) if v["speech_start"] is not None else max(2.5, len(v["text"].split()) * 0.45)
            if k == 1 and v["speech_start"] is not None: d += v["speech_start"]
            sc = {"i": k, "start": t, "dur": d, "text": v["text"], "video": None}
            if clips:
                ci = v.get("clip") or (rr % len(clips) + 1); rr += 1
                ci = min(max(ci, 1), len(clips)); off = offs.get(ci, 0.0)
                p = AS / f"s{k}.mp4"; seg_video(ci, p, d, off); offs[ci] = (off + d) % max(clips[ci - 1]["dur"], 1)
                sc["video"] = f"s{k}.mp4"
            scenes.append(sc); t += d
    return scenes, t

def group_words(words, n, gap=0.5):
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= n or w["s"] - cur[-1]["e"] >= gap or re.search(r"[.!?।]$", cur[-1]["t"])): groups.append(cur); cur = []
        cur.append(w)
    if cur: groups.append(cur)
    return groups

def captions_block(words, P, st, style):
    reel = st["reel"]; n = 3 if reel else 6
    gs = group_words(words, n); html, js = [], []
    base = "#ffffff"
    for k, g in enumerate(gs):
        s = max(0.1, g[0]["s"] - 0.05); e = max(g[-1]["e"], s + 0.45) + 0.05
        if k + 1 < len(gs): e = min(e, max(s + 0.25, gs[k + 1][0]["s"] - 0.05))
        spans = "".join(f'<span class="cw" id="cw{k}_{j}">{esc(w["t"])}</span> ' for j, w in enumerate(g))
        html.append(f'<div id="cg{k}" class="clip layer capl" data-start="{f3(s)}" data-duration="{f3(e - s)}" data-track-index="6"><div id="ci{k}" class="capin">{spans}</div></div>')
        js.append(f'tl.fromTo("#ci{k}",{{opacity:0,y:14,scale:0.94}},{{opacity:1,y:0,scale:1,duration:0.12,ease:"power2.out"}},{f3(s)});')
        for j, w in enumerate(g):
            ws, we = f3(max(s, w["s"])), f3(min(e - 0.05, max(w["e"], w["s"] + 0.1)))
            if style == "pop":
                js.append(f'tl.fromTo("#cw{k}_{j}",{{opacity:0,scale:0.6}},{{opacity:1,scale:1,duration:0.12,ease:"back.out(2)"}},{ws});')
            elif style == "karaoke":
                js.append(f'tl.fromTo("#cw{k}_{j}",{{color:"{base}"}},{{color:"{P["accent"]}",duration:0.06}},{ws});tl.to("#cw{k}_{j}",{{color:"{base}",duration:0.06}},{we});')
        js.append(f'tl.to("#ci{k}",{{opacity:0,duration:0.08}},{f3(e - 0.1)});tl.set("#ci{k}",{{opacity:0}},{f3(e)});')
    pop0 = "opacity:0;" if style == "pop" else ""
    size = (74 if reel else 54); bottom = 560 if reel else 96
    css = (f'.capl{{display:flex;align-items:flex-end;justify-content:center;padding-bottom:{bottom}px}}'
           f'.capin{{width:{int(st["W"] * 0.82)}px;text-align:center;font-weight:800;font-size:{size}px;line-height:1.18;color:#fff;'
           f'text-shadow:0 3px 14px rgba(0,0,0,.85),0 0 3px rgba(0,0,0,.9);{"text-transform:uppercase;" if style == "karaoke" else ""}}}'
           f'.cw{{display:inline-block;{pop0}}}')
    return "\n".join(html), "\n".join(js), css

def grade_attr(sp, P):
    g = sp.get("grade") or {}
    return json.dumps({"preset": g.get("preset") or P["grade"], "intensity": float(g.get("intensity", P["gi"]))}, separators=(",", ":"))

def build_html(sp, st, P, scenes, total, es, ed):
    W, H_, reel = st["W"], st["H"], st["reel"]
    cp = sp.get("captions", {}) or {}; cstyle = cp.get("style") or P["cap"]
    chtml, cjs, ccss = ("", "", "")
    if cp.get("on", True) and st.get("words"): chtml, cjs, ccss = captions_block(st["words"], P, st, cstyle)
    ga = grade_attr(sp, P); L, JS = [], []
    light = P["bg1"].lower().startswith("#f")
    ink = "#111" if light else "#fff"
    for sc in scenes:
        i, a, d = sc["i"], sc["start"], sc["dur"]
        if sc.get("video"):
            L.append(f'<div class="zoom" id="z{i}"><video id="v{i}" class="clip fill" src="assets/{sc["video"]}" muted playsinline data-start="{f3(a)}" data-duration="{f3(d)}" data-track-index="1" data-color-grading=\'{ga}\'></video></div>')
            if P["move"] == "punch": mv = f'tl.fromTo("#z{i}",{{scale:{P["zoom"]}}},{{scale:1,duration:{f3(min(0.5, d))},ease:"power3.out"}},{f3(a)});'
            else: mv = f'tl.fromTo("#z{i}",{{scale:1}},{{scale:{P["zoom"]},duration:{f3(d)},ease:"none"}},{f3(a)});'
            JS.append(f'tl.set("#z{i}",{{opacity:0}},0);tl.fromTo("#z{i}",{{opacity:0}},{{opacity:1,duration:0.2,ease:"power1.out"}},{f3(a)});{mv}tl.set("#z{i}",{{opacity:0}},{f3(a + d)});')
        elif sc.get("text"):
            ws = sc["text"].split()
            spans = "".join(f'<span class="kw" id="k{i}_{j}">{esc(w)}</span> ' for j, w in enumerate(ws))
            L.append(f'<div id="kc{i}" class="clip layer kcard" data-start="{f3(a)}" data-duration="{f3(d)}" data-track-index="2"><div id="kin{i}" class="kin">{spans}</div></div>')
            step = min(0.18, max(0.05, (d * 0.6) / max(len(ws), 1)))
            JS.append(f'tl.fromTo("#kin{i}",{{opacity:0,scale:0.96}},{{opacity:1,scale:1,duration:0.25,ease:"power2.out"}},{f3(a)});')
            JS.append("".join(f'tl.fromTo("#k{i}_{j}",{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.3,ease:"back.out(1.5)"}},{f3(a + 0.1 + j * step)});' for j in range(len(ws))))
            JS.append(f'tl.to("#kin{i}",{{opacity:0,duration:0.15}},{f3(a + d - 0.18)});')
    hook = (sp.get("hook") or "").strip()
    if hook:
        L.append(f'<div id="hook" class="clip layer hookl" data-start="0.3" data-duration="2.5" data-track-index="5"><div id="hookin" class="hookin">{esc(hook)}</div></div>')
        JS.append('tl.fromTo("#hookin",{opacity:0,y:30,scale:0.92},{opacity:1,y:0,scale:1,duration:0.35,ease:"back.out(1.6)"},0.3);tl.to("#hookin",{opacity:0,duration:0.25},2.5);')
    title = (sp.get("title") or "").strip()
    if P["lower"] and title and not reel:
        L.append(f'<div id="lt" class="clip layer ltl" data-start="0.8" data-duration="4" data-track-index="5"><div id="ltin" class="ltin"><i></i><b>{esc(title)}</b></div></div>')
        JS.append('tl.fromTo("#ltin",{opacity:0,x:-60},{opacity:1,x:0,duration:0.4,ease:"power3.out"},0.8);tl.to("#ltin",{opacity:0,duration:0.3},4.4);')
    ec = sp.get("endcard") or {}
    if ec.get("on", True) and ed > 0:
        t1, t2 = esc(ec.get("text") or "Like • Share • Follow"), esc(ec.get("sub") or "")
        btn = esc(ec.get("button") or "FOLLOW")
        L.append(f'<div id="end" class="clip layer" data-start="{f3(es)}" data-duration="{f3(ed)}" data-track-index="8"><div id="endin" class="endin"><div class="e1">{t1}</div><div class="e2">{t2}</div>'
                 + (f'<div id="endbtn" class="btn">{btn}</div>' if P["end"] == "card" else "") + '</div></div>')
        JS.append(f'tl.fromTo("#endin",{{opacity:0}},{{opacity:1,duration:0.35,ease:"power1.out"}},{f3(es)});')
        if P["end"] == "card": JS.append(f'tl.fromTo("#endbtn",{{scale:1}},{{scale:1.1,duration:0.45,yoyo:true,repeat:3,ease:"sine.inOut"}},{f3(es + 0.6)});')
    pbar = '<div id="pbar"></div>' if P["bar"] else ""
    if pbar: JS.append(f'tl.fromTo("#pbar",{{scaleX:0}},{{scaleX:1,duration:{f3(total)},ease:"none"}},0);')
    bars = '<div class="lb t"></div><div class="lb b"></div>' if (P["bars"] and not reel) else ""
    font = P["font"]
    css = f"""
@font-face{{font-family:"FocusDev";src:local("Noto Sans Devanagari"),local("NotoSansDevanagari");}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H_}px;overflow:hidden;background:{P["bg1"]}}}
#root{{position:absolute;left:0;top:0;width:{W}px;height:{H_}px;overflow:hidden;font-family:"{font}","FocusDev",sans-serif;color:{ink}}}
.layer{{position:absolute;left:0;top:0;width:100%;height:100%}}
.bg{{background:linear-gradient(160deg,{P["bg1"]},{P["bg2"]})}}
.blob{{position:absolute;border-radius:50%;filter:blur(90px);opacity:.35;background:{P["accent"]}}}
.zoom{{position:absolute;left:0;top:0;width:100%;height:100%;transform-origin:50% 50%}}
.fill{{position:absolute;left:0;top:0;width:{W}px;height:{H_}px;object-fit:cover}}
.kcard{{display:flex;align-items:center;justify-content:center}}
.kin{{width:{int(W * 0.8)}px;text-align:center;font-weight:800;font-size:{84 if reel else 72}px;line-height:1.2}}
.kw{{display:inline-block}}
.hookl{{display:flex;justify-content:center;padding-top:{int(H_ * 0.12)}px}}
.hookin{{height:fit-content;max-width:{int(W * 0.82)}px;text-align:center;font-weight:900;font-size:{64 if reel else 52}px;padding:18px 34px;border-radius:22px;background:{P["accent"]};color:#000;box-shadow:0 10px 40px rgba(0,0,0,.4)}}
.ltl{{display:flex;align-items:flex-end;padding:0 0 {int(H_ * 0.12)}px {int(W * 0.06)}px}}
.ltin{{display:flex;align-items:center;gap:18px;padding:16px 30px;background:rgba(0,0,0,.65);font-size:44px}}.ltin i{{width:10px;height:56px;background:{P["accent"]}}}
.endin{{position:absolute;left:0;top:0;width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;background:linear-gradient(160deg,{P["bg1"]},{P["bg2"]});text-align:center;padding:0 {int(W * 0.08)}px}}
.e1{{font-weight:900;font-size:{78 if reel else 80}px}}.e2{{font-size:{42 if reel else 40}px;opacity:.8}}
.btn{{margin-top:20px;padding:22px 64px;border-radius:999px;background:{P["accent"]};color:#000;font-weight:900;font-size:46px}}
#pbar{{position:absolute;left:0;top:0;width:100%;height:10px;background:{P["accent"]};transform-origin:0 50%;z-index:30}}
.lb{{position:absolute;left:0;width:100%;height:9%;background:#000;z-index:25}}.lb.t{{top:0}}.lb.b{{bottom:0}}
{ccss}"""
    blobs = (f'<div class="blob" id="b1" style="width:{int(W*.5)}px;height:{int(W*.5)}px;left:-10%;top:10%"></div>'
             f'<div class="blob" id="b2" style="width:{int(W*.4)}px;height:{int(W*.4)}px;right:-10%;bottom:5%"></div>')
    JS.insert(0, f'tl.to("#b1",{{x:{int(W*.25)},y:{int(-H_*.08)},duration:{f3(total)},ease:"sine.inOut"}},0);tl.to("#b2",{{x:{int(-W*.25)},y:{int(H_*.08)},duration:{f3(total)},ease:"sine.inOut"}},0);')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width={W}, height={H_}">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{f3(total)}" data-width="{W}" data-height="{H_}">
<div class="layer bg" data-layout-ignore>{blobs}</div>
{chr(10).join(L)}
{chtml}
{bars}{pbar}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(JS)}
{cjs}
window.__timelines["main"] = tl;
</script></body></html>"""

def stage_compose():
    sp, st = S(), ST()
    P = dict(PRESETS.get(sp.get("preset") or DEFAULT, PRESETS[DEFAULT]))
    scenes, t = build_scenes(sp, st)
    if st.get("voice") and st["voice_dur"] + 0.3 > t:
        if sp.get("kind") != "faceless": warn(st, "voice is longer than the clips; the tail will have no picture")
        t = max(t, st["voice_dur"] + 0.3)
    ec = sp.get("endcard") or {}
    ed = 3.0 if ec.get("on", True) else 0.0
    es = t; total = t + ed
    if not scenes: raise RuntimeError("nothing to render: add clips or a script")
    st.update(scenes=scenes, total=total, end_start=es, end_dur=ed); save(st)
    custom = (sp.get("html") or "").strip()
    if custom:
        tok = {"W": st["W"], "H": st["H"], "TOTAL": f3(total), "ENDCARD_START": f3(es), "VOICE_DUR": f3(st.get("voice_dur", 0))}
        for sc in scenes: tok[f"S{sc['i']}_START"] = f3(sc["start"]); tok[f"S{sc['i']}_DUR"] = f3(sc["dur"])
        for k, v in tok.items(): custom = custom.replace("{{" + k + "}}", str(v))
        if "<!--FOCUS_CAPTIONS-->" in custom and sp.get("captions", {}).get("on", True) and st.get("words"):
            ch, cj, cc = captions_block(st["words"], P, st, (sp.get("captions") or {}).get("style") or P["cap"])
            custom = custom.replace("<!--FOCUS_CAPTIONS-->", ch).replace("/*FOCUS_CAPTIONS_JS*/", cj)
            custom = custom.replace("</head>", f"<style>{cc}</style></head>", 1)
        html = custom; st["custom"] = True
    else:
        html = build_html(sp, st, P, scenes, total, es, ed); st["custom"] = False
    (PROJ / "index.html").write_text(html, "utf-8"); st["own_audio"] = bool(re.search(r"<audio\b", html)); save(st)
    if not DRY:
        r = sh(HF + ["check", "--json"], cwd=PROJ, check=False, cap=True)
        (OUT / "check.json").write_text((r.stdout or "") + (r.stderr or ""), "utf-8")
        log("hyperframes check exit code:", r.returncode, "(see out/check.json)")

# ---------------------------------------------------------------- render + finish
def stage_render():
    st = ST(); target = WORK / "render.mp4"
    if DRY:
        ff("-f", "lavfi", "-i", f"color=c=0x203040:s={st['W']}x{st['H']}:d={st['total']:.2f}:r=30", "-pix_fmt", "yuv420p", str(target)); return
    sh(HF + ["render", "--output", str(target), "--fps", "30", "--quality", os.environ.get("FOCUS_QUALITY", "standard")], cwd=PROJ)
    if not target.exists(): raise RuntimeError("render finished but no video was produced")

def synth_music(style, total, out):
    ch = {"calm": [130.8, 164.8, 196.0, 246.9], "upbeat": [196.0, 246.9, 293.7, 392.0], "dark": [110.0, 130.8, 164.8, 220.0], "epic": [98.0, 146.8, 196.0, 293.7]}.get(style, [130.8, 164.8, 196.0, 246.9])
    ex = "+".join(f"0.18*sin(2*PI*{f}*t)*(0.6+0.4*sin(2*PI*{0.1 + 0.03 * k}*t))" for k, f in enumerate(ch))
    if style == "upbeat": ex += "+0.12*sin(2*PI*65.4*t)*pow(abs(sin(2*PI*2*t)),4)"
    ff("-f", "lavfi", "-i", f"aevalsrc='{ex}':d={total:.2f}:s=48000", "-af", "lowpass=f=1800,aecho=0.8:0.7:90:0.35", str(out))

def stage_finish():
    sp, st = S(), ST(); total = st["total"]; render = WORK / "render.mp4"; final = OUT / "final.mp4"
    m = sp.get("music") or {}
    mus = None
    if m.get("source") == "upload" and (TMP / "music_in").exists(): mus = TMP / "music_in"
    elif m.get("source") == "synth" or st.get("dsl_music"):
        mus = TMP / "music_syn.wav"; synth_music(m.get("style") or st.get("dsl_music") or "calm", total, str(mus))
    base = None
    if st.get("voice"): base = AS / "voice.wav"
    elif sp.get("kind") != "faceless" and st["clips"] and not sp.get("mute_original"):
        ins = []
        for c in st["clips"]: ins += ["-i", str(AS / f"clip{c['i']}.mp4")]
        n = len(st["clips"]); fg = "".join(f"[{k}:a]" for k in range(n)) + f"concat=n={n}:v=0:a=1[o]"
        ff(*ins, "-filter_complex", fg, "-map", "[o]", "-ar", "48000", "-ac", "1", str(TMP / "orig48.wav"))
        ff("-i", str(TMP / "orig48.wav"), "-af", CLEAN if (sp.get("voice") or {}).get("cleanup", True) else "anull", str(TMP / "orig_clean.wav"))
        base = TMP / "orig_clean.wav"
    if st.get("own_audio"): shutil.copy(render, final)
    elif base is None and mus is None: shutil.copy(render, final)
    else:
        # ffmpeg inputs: 0 = rendered video, 1 = base audio (voice / original clip audio / silence), 2 = music
        base_in = ["-i", str(base)] if base is not None else ["-f", "lavfi", "-t", f3(total), "-i", "anullsrc=r=48000:cl=mono"]
        if mus is not None:
            gain = float(m.get("volume", 0.16))
            fg = (f"[2:a]volume={gain},atrim=0:{total:.2f},afade=t=in:d=1,afade=t=out:st={max(total - 2, 0):.2f}:d=2,asetpts=PTS-STARTPTS[m];"
                  f"[1:a]apad,atrim=0:{total:.2f},asplit=2[b][sc];[m][sc]sidechaincompress=threshold=0.04:ratio=10:attack=15:release=350[md];"
                  "[b][md]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11[o]")
            ff("-i", str(render), *base_in, "-stream_loop", "-1", "-i", str(mus), "-filter_complex", fg, "-map", "0:v", "-map", "[o]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f3(total), str(final))
        else:
            fg = f"[1:a]apad,atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[o]"
            ff("-i", str(render), *base_in, "-filter_complex", fg, "-map", "0:v", "-map", "[o]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f3(total), str(final))
    for n, frac in enumerate((0.12, 0.4, 0.7), 1):
        ff("-ss", f3(total * frac), "-i", str(final), "-frames:v", "1", "-q:v", "2", str(OUT / f"thumb{n}.jpg"))
    words = st.get("words", []); text = " ".join(w["t"] for w in words)
    (OUT / "transcript.txt").write_text(text or "\n".join(s["text"] for s in st["scenes"] if s.get("text")), "utf-8")
    jd(OUT / "meta_src.json", {"title": sp.get("title", ""), "script": sp.get("script", ""), "transcript": text, "duration": round(total, 1),
                                "format": sp.get("format"), "kind": sp.get("kind"), "preset": sp.get("preset"), "lang": (sp.get("voice") or {}).get("lang")})
    shutil.copy(PROJ / "index.html", OUT / "composition.html"); shutil.copy(WORK / "spec.json", OUT / "spec.json")
    jd(OUT / "report.json", {"ok": True, "duration": round(total, 1), "warnings": st.get("warnings", []), "size_mb": round(final.stat().st_size / 1e6, 1)})
    _names = sorted(x.name for x in OUT.iterdir() if x.is_file()) + ["manifest.json"]
    jd(OUT / "manifest.json", {"job": sp.get("id", ""), "title": sp.get("title", ""), "created": sp.get("created", ""),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": sp.get("kind", ""), "mode": sp.get("mode", ""),
        "preset": sp.get("preset", ""), "format": sp.get("format", ""), "duration": round(total, 1),
        "custom_html": bool(st.get("custom")), "warnings": st.get("warnings", []), "files": sorted(set(_names))})
    log("done:", final, f"{final.stat().st_size / 1e6:.1f} MB")

if __name__ == "__main__":
    st_ = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"fetch": stage_fetch, "voice": stage_voice, "captions": stage_captions, "compose": stage_compose, "render": stage_render, "finish": stage_finish}.get(st_)
    if not fn: sys.exit("usage: pipeline.py fetch|voice|captions|compose|render|finish")
    try: fn()
    except Exception as e:
        OUT.mkdir(parents=True, exist_ok=True); jd(OUT / "report.json", {"ok": False, "stage": st_, "error": str(e)[:1500]})
        print("FAILED:", e, file=sys.stderr); sys.exit(1)
