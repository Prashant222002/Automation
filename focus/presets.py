"""NeuroTriage Advance Engine presets. Grades use HyperFrames' own built-in color-grading presets (data-color-grading)."""
PRESETS = {
  "cinematic":   dict(label="Cinematic",   grade="muted-editorial", gi=1.0, font="Playfair Display", accent="#e8c07a", bg1="#0b0b12", bg2="#1b1b2b", cap="clean",   zoom=1.07, move="slow",  bars=True,  end="fade", lower=False, bar=False),
  "vlog":        dict(label="Vlog",        grade="warm-daylight",   gi=1.0, font="Poppins",          accent="#ffd166", bg1="#14110f", bg2="#2b2118", cap="pop",     zoom=1.05, move="slow",  bars=False, end="card", lower=False, bar=False),
  "news":        dict(label="News",        grade="clean-studio",    gi=1.0, font="Oswald",           accent="#e63946", bg1="#08121f", bg2="#10243d", cap="clean",   zoom=1.03, move="slow",  bars=False, end="card", lower=True,  bar=False),
  "viral":       dict(label="Viral Reel",  grade="bright-pop",      gi=1.0, font="Montserrat",       accent="#00f5d4", bg1="#0d0221", bg2="#261447", cap="karaoke", zoom=1.14, move="punch", bars=False, end="card", lower=False, bar=True),
  "minimal":     dict(label="Minimal",     grade="soft-boost",      gi=0.8, font="Inter",            accent="#ffffff", bg1="#f4f1ea", bg2="#e4dfd3", cap="clean",   zoom=1.03, move="slow",  bars=False, end="fade", lower=False, bar=False),
  "neon":        dict(label="Neon Night",  grade="deep-contrast",   gi=1.0, font="Outfit",           accent="#ff2bd6", bg1="#05010d", bg2="#1a0638", cap="karaoke", zoom=1.10, move="punch", bars=False, end="card", lower=False, bar=True),
  "documentary": dict(label="Documentary", grade="mono-fade",       gi=0.6, font="EB Garamond",      accent="#d9d2c3", bg1="#101010", bg2="#232323", cap="clean",   zoom=1.06, move="slow",  bars=True,  end="fade", lower=True,  bar=False),
  "retro":       dict(label="Retro VHS",   grade="vhs-playback",    gi=1.0, font="Space Mono",       accent="#ffb703", bg1="#120a05", bg2="#2a1a0c", cap="pop",     zoom=1.05, move="slow",  bars=False, end="card", lower=False, bar=False),
}
DEFAULT = "viral"
GRADES = ["neutral","warm-daylight","clean-studio","skin-soft","food-pop","night-lift","muted-editorial","vintage-wash",
          "mono-clean","mono-fade","soft-boost","bright-pop","deep-contrast","creator-camcorder","vhs-playback"]
VOICES = {"hi": ["hf_alpha","hf_beta","hm_omega","hm_psi"], "en": ["af_heart","am_adam","bf_emma","bm_george"]}
EDGE = {"hi": "hi-IN-SwaraNeural", "en": "en-US-AriaNeural"}   # fallback if Kokoro is unavailable
