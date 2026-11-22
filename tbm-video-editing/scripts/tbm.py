#!/usr/bin/env python3
"""TBM video editing pipeline: long video / podcast / raw recording -> vertical reels + ads.

Run with the skill's venv python (has opencv + numpy):
    PY=~/.tbm-video-work/.venv/bin/python   (Windows: ~/.tbm-video-work/.venv/Scripts/python.exe)
    $PY tbm.py <command> --project <dir> [...]

Commands
  check-setup                      verify ffmpeg / whisper / opencv / fonts
  fetch    <url-or-path>           put the source video in <project>/source.mp4 (Google Drive public links ok)
  transcribe                       full-source transcript -> <project>/transcript.txt (+ words json)
  probe    [--times t1,t2,...]     sample frames with numbered faces -> <project>/probe/*.jpg (to pick the main speaker)
  set-speaker --time T --face K    store the main speaker's look (shirt colour) in config.json
  words    <clip>                  print the clip transcript with absolute timestamps + likely host interjections
  build    <clip|all>              render reel (and ad if clip has "ad": true)
  check    [clip|all]              quality checks: flash frames, faces under text, host words, contact sheets
All clip times in clips.json are ABSOLUTE seconds in the source video.
"""
import argparse, json, math, os, re, shutil, subprocess, sys, glob

WIN = os.name == "nt"
if WIN and not sys.flags.utf8_mode:   # Windows defaults to cp1252: ₹ and curly quotes in captions would crash. Re-run in UTF-8 mode.
    sys.exit(subprocess.run([sys.executable, "-X", "utf8", *sys.argv]).returncode)
# whisper + yt-dlp live next to the venv python; on Windows ffmpeg lives in WinGet's folder (setup.py notes where)
_extra = [os.path.dirname(sys.executable)]
_fd = os.path.expanduser("~/.tbm-video-work/ffmpeg_dir.txt")
if os.path.exists(_fd): _extra.append(open(_fd).read().strip())
os.environ["PATH"] = os.pathsep.join(_extra + [os.environ.get("PATH", "")])

def subs(path):
    """subtitles filter for an .ass file. Windows paths (C:\\...) must be quoted with the drive colon escaped, and fonts read from the Windows folder"""
    q = lambda p: "'" + os.path.abspath(p).replace("\\", "/").replace(":", "\\:") + "'"
    return f"subtitles={q(path)}" + (f":fontsdir={q(os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts'))}" if WIN else "")

MAC_ONLY_FONTS = {"avenir next demi bold": "Segoe UI Semibold", "avenir next": "Segoe UI", "avenir next bold": "Segoe UI Bold",
                  "helvetica neue": "Arial", "sf pro display": "Segoe UI", "futura": "Century Gothic"}

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

# ---------------------------------------------------------------- utils
def sh(cmd, **kw):
    kw.setdefault("check", True)
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, **kw)

def ff(*args):
    sh(["ffmpeg", "-y", "-v", "error", *args])

def probe(src):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", src],
                         capture_output=True, text=True).stdout
    j = json.loads(out); s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), float(j["format"]["duration"])

def load_json(p, default=None):
    return json.load(open(p)) if os.path.exists(p) else default

def WORK(P):
    """heavy files (source video, temp renders) live on the laptop, never in a Drive-synced project"""
    import hashlib
    d = os.path.join(os.path.expanduser("~/.tbm-video-work"), re.sub(r"\W+", "_", os.path.basename(P.rstrip("/")))[:40] + "_" + hashlib.md5(P.encode()).hexdigest()[:8])
    os.makedirs(d, exist_ok=True); return d

def SRC(P): return os.path.join(WORK(P), "source.mp4")

def cfg_of(P):
    c = load_json(os.path.join(SKILL, "config.default.json"))
    user = load_json(os.path.join(P, "config.json"), {})
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict): c[k].update(v)
        else: c[k] = v
    if WIN:   # Mac fonts don't exist on Windows: use the nearest Windows font so captions keep their weight
        def swap(d):
            for k, v in list(d.items()):
                if isinstance(v, dict): swap(v)
                elif k.endswith("font") and isinstance(v, str) and v.lower() in MAC_ONLY_FONTS: d[k] = MAC_ONLY_FONTS[v.lower()]
        swap(c)
    return c

def clips_of(P):
    return load_json(os.path.join(P, "clips.json"), [])

def hex2ass(h):  # "#RRGGBB" -> &H00BBGGRR
    h = h.lstrip("#"); return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()

def whisper(audio, outdir, cfg, words=True, model=None):
    lang = cfg.get("language", "en")
    model = model or (cfg["whisper_clip_model"] if lang == "en" else cfg["whisper_clip_model"].replace(".en", ""))
    cmd = ["whisper", audio, "--model", model, "--output_format", "json", "--output_dir", outdir, "--fp16", "False"]
    if words: cmd += ["--word_timestamps", "True"]
    if lang: cmd += ["--language", lang]
    sh(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(outdir, os.path.splitext(os.path.basename(audio))[0] + ".json")

def words_from(js):
    w = []
    for s in json.load(open(js))["segments"]:
        for x in s.get("words", []):
            t = x["word"].strip()
            if t: w.append([float(x["start"]), float(x["end"]), t])
    for i in range(1, len(w)):   # monotonic timing
        if w[i][0] < w[i-1][0] + 0.03: w[i][0] = w[i-1][0] + 0.03
        if w[i][1] < w[i][0]: w[i][1] = w[i][0] + 0.05
    return w

# ---------------------------------------------------------------- setup / fetch / transcribe
def cmd_check_setup(a):
    ok = True
    for tool in ["ffmpeg", "ffprobe", "whisper"]:
        p = shutil.which(tool); print(f"{tool:8s} {'OK ' + p if p else 'MISSING'}"); ok &= bool(p)
    try:
        import cv2, numpy; print("opencv   OK", cv2.__version__); cv2.CascadeClassifier
    except Exception as e:
        print("opencv   MISSING (run scripts/setup.py)", e); ok = False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    has = " subtitles " in out; print("libass   " + ("OK" if has else "MISSING: install ffmpeg with libass (run scripts/setup.py)")); ok &= has
    print("READY" if ok else "NOT READY")
    if not ok: sys.exit(1)

def cmd_fetch(a):
    P = a.project; os.makedirs(P, exist_ok=True); dst = SRC(P)
    src = a.src
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=)([\w-]+)", src)
    if m:
        url = f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
        sh(["curl", "-L", "--fail", "-o", dst, url])
    elif re.search(r"(youtube\.com|youtu\.be)/", src):
        if not shutil.which("yt-dlp"): raise SystemExit("yt-dlp missing: run scripts/setup.py")
        sh(["yt-dlp", "-f", "bv*[height<=2160]+ba/b", "--merge-output-format", "mp4", "-o", dst, src])
    elif src.startswith("http"):
        sh(["curl", "-L", "--fail", "-o", dst, src])
    else:
        if os.path.abspath(src) != os.path.abspath(dst): os.symlink(os.path.abspath(src), dst) if not os.path.exists(dst) else None
    w, h, fps, d = probe(dst)
    print(f"source.mp4  {w}x{h}  {fps:.2f}fps  {d/60:.1f} min")

def cmd_transcribe(a):
    P = a.project; cfg = cfg_of(P); work = WORK(P); os.makedirs(work, exist_ok=True)
    wav = os.path.join(work, "source.wav")
    if not os.path.exists(wav): ff("-i", SRC(P), "-vn", "-ac", "1", "-ar", "16000", wav)
    lang = cfg.get("language", "en")
    model = cfg["whisper_full_model"] if lang == "en" else cfg["whisper_full_model"].replace(".en", "")
    js = whisper(wav, work, cfg, words=True, model=model)
    with open(os.path.join(P, "transcript.txt"), "w") as f:
        for s in json.load(open(js))["segments"]:
            t = s["start"]; f.write(f"[{int(t)//60}:{int(t)%60:02d} | {t:.1f}s] {s['text'].strip()}\n")
    print("wrote", os.path.join(P, "transcript.txt"))

# ---------------------------------------------------------------- vision helpers
def _cv():
    import cv2, numpy as np
    return cv2, np

def chest_lab(img, face):
    cv2, np = _cv()
    x, y, w, h = face; H, W = img.shape[:2]
    x0, y0 = int(max(0, x - 0.3*w)), int(min(H-1, y + 1.6*h)); x1, y1 = int(min(W, x + 1.3*w)), int(min(H, y + 2.6*h))
    r = img[y0:y1, x0:x1]
    if r.size < 300: return None
    lab = cv2.cvtColor(r, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
    return [float(v) for v in np.median(lab, axis=0)]

def faces_in(gray, minsize=30):
    cv2, np = _cv()
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    fs = casc.detectMultiScale(gray, 1.1, 5, minSize=(minsize, minsize))
    return sorted([tuple(int(v) for v in f) for f in fs], key=lambda r: -r[2]*r[3])

def read_frames(src, W, H, ss=None, t=None, fps=None, color=True, n=None):
    cv2, np = _cv()
    cmd = ["ffmpeg", "-v", "error"]
    if ss is not None: cmd += ["-ss", f"{ss:.3f}"]
    if t is not None: cmd += ["-t", f"{t:.3f}"]
    vf = (f"fps={fps}," if fps else "") + f"scale={W}:{H},format={'bgr24' if color else 'gray'}"
    tail = ["-frames:v", str(n)] if n else []
    raw = subprocess.run(cmd + ["-i", src, "-vf", vf] + tail + ["-f", "rawvideo", "-"], capture_output=True, stdin=subprocess.DEVNULL).stdout
    c = 3 if color else 1
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, c) if color else np.frombuffer(raw, np.uint8).reshape(-1, H, W)

def cmd_probe(a):
    cv2, np = _cv()
    P = a.project; src = SRC(P); w, h, fps, d = probe(src)
    times = [float(t) for t in a.times.split(",")] if a.times else [d*f for f in (0.15, 0.35, 0.55, 0.75)]
    od = os.path.join(P, "probe"); os.makedirs(od, exist_ok=True)
    W = 960; H = int(round(h * W / w / 2) * 2)
    info = {}
    for t in times:
        f = read_frames(src, W, H, ss=t, n=1)[0].copy()
        fs = faces_in(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
        fs = [x for x in fs if fs and x[2] >= 0.5 * fs[0][2]]
        info[str(t)] = []
        for k, fc in enumerate(fs[:6]):
            x, y, ww, hh = fc
            cv2.rectangle(f, (x, y), (x+ww, y+hh), (0, 255, 255), 2)
            cv2.putText(f, str(k), (x, max(20, y-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            info[str(t)].append({"face": k, "box": fc, "chest_lab": chest_lab(f, fc)})
        cv2.imwrite(os.path.join(od, f"t{t:.1f}.jpg"), f)
    json.dump(info, open(os.path.join(od, "faces.json"), "w"), indent=1)
    print("look at", od, "-> then: set-speaker --time T --face K   (times:", ", ".join(f"{t:.1f}" for t in times), ")")

def cmd_set_speaker(a):
    P = a.project; info = json.load(open(os.path.join(P, "probe", "faces.json")))
    key = min(info.keys(), key=lambda k: abs(float(k) - a.time))
    fc = [x for x in info[key] if x["face"] == a.face][0]
    c = load_json(os.path.join(P, "config.json"), {})
    c.setdefault("main_speaker", {})["chest_lab"] = fc["chest_lab"]
    allf = [x["chest_lab"] for fs in info.values() for x in fs if x["chest_lab"]]
    allf = [v for v in allf if math.dist(v, fc["chest_lab"]) < 40]   # drop false detections (walls, lamps)
    main_c = fc["chest_lab"]; far = max(allf, key=lambda v: math.dist(v, main_c))
    for _ in range(5):   # 2-means: main speaker vs everyone else
        gm = [v for v in allf if math.dist(v, main_c) <= math.dist(v, far)]
        go = [v for v in allf if math.dist(v, main_c) > math.dist(v, far)]
        if not go: break
        main_c = [sum(z) / len(gm) for z in zip(*gm)]; far = [sum(z) / len(go) for z in zip(*go)]
    c["main_speaker"]["chest_lab"] = [round(v, 1) for v in main_c]
    c["main_speaker"]["others_lab"] = [[round(v, 1) for v in far]] if go else []
    w, h, fps, d = probe(SRC(P))
    c["main_speaker"]["side_hint"] = "right" if (fc["box"][0] + fc["box"][2]/2) > 480 else "left"
    json.dump(c, open(os.path.join(P, "config.json"), "w"), indent=1)
    print("main speaker set:", c["main_speaker"])

# ---------------------------------------------------------------- classify shots
def classify(mezz, cfg):
    """per shot: [a, b, kind, face(cx,cy,w as frame fractions)] ; kinds: split | main | wide | other | none"""
    cv2, np = _cv()
    w, h, fps, d = probe(mezz)
    W = 768; H = int(round(h * W / w / 2) * 2)
    fr = read_frames(mezz, W, H)
    ref = cfg.get("main_speaker", {}).get("chest_lab")
    solo = cfg.get("mode") == "solo" or ref is None
    def is_main(img, f):
        if solo: return True
        c = chest_lab(img, f)
        if c is None: return None
        dm = math.dist(c, ref)
        others = cfg.get("main_speaker", {}).get("others_lab") or []
        do = min([math.dist(c, o) for o in others], default=1e9)
        return dm < cfg["speaker_color_tolerance"] and dm < do
    out, cuts, prev = [], [0], None
    vertical = h > w
    for i, f in enumerate(fr):
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY); gf = g.astype(float)
        small = gf[::4, ::4]
        if prev is not None and np.abs(small - prev).mean() > 25: cuts.append(i)
        prev = small
        split = False
        if not vertical:
            col = gf[int(H*0.1):int(H*0.9), W//2-3:W//2+3].mean(axis=0)
            side = np.r_[gf[int(H*0.1):int(H*0.9), W//2-24:W//2-12].mean(), gf[int(H*0.1):int(H*0.9), W//2+12:W//2+24].mean()].mean()
            split = (col.max() - side > 40) or (side - col.min() > 40 and col.min() < 30)
        out.append(["split" if split else "?", None])
    for i in range(1, len(out)):
        if (out[i][0] == "split") != (out[i-1][0] == "split") and i not in cuts: cuts.append(i)
    cuts = sorted(set(cuts)) + [len(out)]
    shots = []
    for a_, b_ in zip(cuts, cuts[1:]):
        if b_ <= a_: continue
        nsplit = sum(1 for x in out[a_:b_] if x[0] == "split")
        samp = list(range(a_, b_, max(1, (b_ - a_) // 6)))[:8]
        if nsplit > (b_ - a_) / 2:
            # main speaker side of a split frame
            side = cfg.get("main_speaker", {}).get("split_side") or cfg.get("main_speaker", {}).get("side_hint") or "right"
            if not solo and ref is not None:
                votes = {"left": 0, "right": 0}
                for i in samp:
                    for sd, sl in (("left", slice(0, W//2)), ("right", slice(W//2, W))):
                        half = fr[i][:, sl]; fs = faces_in(cv2.cvtColor(half, cv2.COLOR_BGR2GRAY))
                        if fs and is_main(half, fs[0]): votes[sd] += 1
                if votes["left"] != votes["right"]: side = max(votes, key=votes.get)
            fx = []
            for i in samp:
                x0 = W//2 if side == "right" else 0
                half = fr[i][:, x0:x0 + W//2]; fs = faces_in(cv2.cvtColor(half, cv2.COLOR_BGR2GRAY))
                if fs: x, y, ww, hh = fs[0]; fx.append([(x0 + x + ww/2)/W, (y + hh/2)/H, ww/W])
            face = [float(np.median([q[j] for q in fx])) for j in range(3)] if fx else [0.75 if side == "right" else 0.25, 0.3, 0.09]
            shots.append([a_, b_, "split", face, side]); continue
        votes = {"main": [], "other": [], "wide": []}
        for i in samp:
            fs = faces_in(cv2.cvtColor(fr[i], cv2.COLOR_BGR2GRAY))
            if not fs: continue
            mains = [f for f in fs if is_main(fr[i], f)]
            pick = mains[0] if mains else None
            if pick is None: votes["other"].append([(fs[0][0]+fs[0][2]/2)/W, (fs[0][1]+fs[0][3]/2)/H, fs[0][2]/W]); continue
            x, y, ww, hh = pick; fc = [(x+ww/2)/W, (y+hh/2)/H, ww/W]
            kind = "wide" if (ww / W < cfg["wide_face_fraction"] and not vertical) else "main"
            votes[kind].append(fc)
        k = max(votes, key=lambda z: len(votes[z]))
        if not votes[k]: shots.append([a_, b_, "none", None, None]); continue
        face = [float(np.median([q[j] for q in votes[k]])) for j in range(3)]
        shots.append([a_, b_, k, face, None])
    return shots

# ---------------------------------------------------------------- render
def snap(t, F): return (math.floor(t * F) + 0.5) / F

def plan_segments(shots, w, h, fps, words, cut_points, cfg):
    """Frame-exact crop plan. Every crop puts the eyes on the same line (cfg eye_line, fraction from top)
    and keeps face size consistent; long shots alternate base/punch-in on phrase starts and at cuts."""
    EYE = cfg.get("eye_line", 0.36); TF = cfg.get("face_width_target", 0.30); PUNCH = cfg.get("punch_in", 1.18)
    vertical = h > w
    minch = h * (0.5 if h >= 2000 else 0.72)
    ev = lambda v: int(v) // 2 * 2
    def rect(face, side, level):
        cx, cy, fw = face[0] * w, face[1] * h, face[2] * w
        eye = cy - 0.12 * fw
        tf = TF * (PUNCH if level else 1.0)
        if vertical: ch = min(h, w * 16 / 9) / (PUNCH if level else 1.0)
        else: ch = (fw / tf) * 16 / 9
        ch = max(minch, min(h, ch))
        if eye - EYE * ch < 0: ch = max(minch, eye / EYE)          # face high in frame: zoom in so eyes reach the line
        cw = ch * 9 / 16
        if cw > w: cw = w; ch = cw * 16 / 9
        lo, hi = (0, w - cw)
        if side == "right": lo, hi = (w / 2, w - cw)
        if side == "left": lo, hi = (0, w / 2 - cw)
        x0 = max(lo, min(hi, cx - cw / 2)); y0 = max(0, min(h - ch, eye - EYE * ch))
        return [ev(x0), ev(y0), ev(cw), ev(ch)]
    # phrase starts (frames) where a punch-in toggle may happen
    starts = sorted(set([int(round(x[0] * fps)) for i, x in enumerate(words) if i == 0 or x[0] - words[i-1][1] > 0.3 or words[i-1][2][-1:] in ".,?!"]))
    cuts_f = sorted(int(round(t * fps)) for t in cut_points)
    segs, last_face, level = [], None, 0
    for a_, b_, k, f, side in shots:
        if k in ("split", "main", "wide") and f: last_face = (f, side if k == "split" else None)
        if last_face is None: segs.append([a_, b_, 0, 0, ev(min(w, h * 9 / 16)), ev(h), k, 0]); continue
        face, sd = last_face
        if k == "wide": face = [face[0], face[1], max(face[2], 0.07)]
        toggles = [a_]
        t = a_
        while True:
            nxt = [c for c in cuts_f if t + fps * 0.5 < c < b_ - fps * 0.5] + [s_ for s_ in starts if t + fps * 3.0 <= s_ < b_ - fps * 1.5]
            if not nxt: break
            t = min(nxt); toggles.append(t)
        toggles.append(b_)
        for i, (x, y) in enumerate(zip(toggles, toggles[1:])):
            if y - x < 2: continue
            lv = level if i == 0 else (1 - segs[-1][7])
            segs.append([x, y] + rect(face, sd, lv) + [k, lv])
        level = 0   # each new camera shot starts at base framing
    return segs

def render_vertical(mezz, shots, out, broll, cfg, words=(), cut_points=()):
    w, h, fps, d = probe(mezz); F = round(fps); N = shots[-1][1]
    shots = [s_ for s_ in shots if s_[0] < N]
    segs = plan_segments(shots, w, h, F, list(words), list(cut_points), cfg)
    tmp = out + ".parts"; os.makedirs(tmp, exist_ok=True); parts = []
    for i, (a_, b_, x, y, cw, ch, k, lv) in enumerate(segs):
        p = os.path.join(tmp, f"p{i:03d}.mp4")
        ff("-ss", f"{max(0, (a_ - 0.4) / F):.4f}", "-i", mezz, "-frames:v", str(b_ - a_), "-an",
           "-vf", f"crop={cw}:{ch}:{x}:{y},scale=1080:1920:flags=lanczos,setsar=1",
           "-r", str(F), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", p)
        parts.append(p)
    lst = os.path.join(tmp, "list.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(p).replace(os.sep, '/')}'\n" for p in parts))
    joined = os.path.join(tmp, "joined.mp4")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-i", mezz, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", joined)
    if broll:
        ins = ["-i", joined]; fc = ""; last = "0:v"
        for j, (t0, t1, fpath) in enumerate(broll):
            ins += ["-i", fpath]
            fc += (f"[{j+1}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps={F},setsar=1,"
                   f"trim=0:{t1-t0:.3f},setpts=PTS-STARTPTS+{t0:.3f}/TB[b{j}];[{last}][b{j}]overlay=0:0:eof_action=pass:enable='between(t,{t0:.3f},{t1:.3f})'[v{j}];")
            last = f"v{j}"
        ff(*ins, "-filter_complex", fc.rstrip(";"), "-map", f"[{last}]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "copy", out)
    else:
        shutil.move(joined, out)
    shutil.rmtree(tmp, ignore_errors=True)
    covered = lambda a_, b_: any(t0 * F <= a_ + 2 and t1 * F >= b_ - 2 for t0, t1, _ in broll)
    return [[round(s_[0]/F, 2), round(s_[1]/F, 2)] for s_ in segs if s_[6] in ("other", "none") and (s_[1]-s_[0]) > F*0.3 and not covered(s_[0], s_[1])]

# ---------------------------------------------------------------- captions
STOP = set(("a an the to of and or but is are was were i you he she it we they my your our their this that these those in on at for with from by as be been so if then than not do does did have has had will would can could just like very also about into up out me him her them us there here what who how when where why which "
            "going something things thing really people because actually basically there's that's it's i'm don't let's suppose").split())
WL = set("cold warm hot call lead leads sales why viral money debt fear fail goal life lakh crore crores webinar story trust offer love pain".split())
def strong(t):
    k = re.sub(r"[^\w%₹$']", "", t).lower()
    return (k not in STOP and (len(k) >= 5 or k in WL)) or any(ch.isdigit() for ch in k)

def apply_fixes(words, fixes):
    for bad, good in fixes.items():
        b = bad.lower().split(); i = 0
        while i <= len(words) - len(b):
            if [re.sub(r"[^\w']", "", x[2]).lower() for x in words[i:i+len(b)]] == b:
                tail = re.sub(r"^[\w']+", "", words[i+len(b)-1][2].split()[-1])
                words[i:i+len(b)] = [[words[i][0], words[i+len(b)-1][1], (good + tail) if good else ""]]
            i += 1
    m = []
    for w in words:
        if m and w[2].strip().startswith("%"): m[-1][2] += w[2].strip(); m[-1][1] = w[1]; continue   # whisper splits "20 %"
        if not re.sub(r"[\W_]", "", w[2]): continue
        if m and (w[2].startswith("-") or w[2].startswith("'")): m[-1][2] += w[2]; m[-1][1] = w[1]
        else: m.append(list(w))
    return m

def remap(words, keep):
    out = []
    for a_, b_, t in words:
        acc = 0
        for k0, k1 in keep:
            if k0 - 0.03 <= a_ and b_ <= k1 + 0.08: out.append([a_ - k0 + acc, min(b_, k1) - k0 + acc, t]); break
            acc += k1 - k0
    return out

def T(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t - h*3600 - m*60
    return f"{h}:{m:02d}:{s:05.2f}"

def captions_brand(words, cfg, out):
    C = cfg["captions"]
    words = [[a_, b_, re.sub(r"[,;]+", "", t), bool(re.search(r"[,;.?!]$", t))] for a_, b_, t in words]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        alone = len(cur) == 1 and not strong(w[2])
        if (w[3] and not alone) or len(cur) >= 6 or sum(len(x[2]) + 1 for x in cur) >= 22 or (len(cur) >= 2 and strong(w[2])): chunks.append(cur); cur = []   # 22 chars keeps the small line inside 1080px
    if cur:
        if chunks and len(cur) == 1: chunks[-1] += cur
        else: chunks.append(cur)
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if not strong(c[-1][2]) and not c[-1][3]:
            st = [j for j in range(len(c) - 1) if strong(c[j][2])]
            if st and i + 1 < len(chunks): j = st[-1]; chunks[i] = c[:j+1]; chunks[i+1] = c[j+1:] + chunks[i+1]
        i += 1
    low = lambda ws: " ".join(w if (len(w) > 1 and re.sub(r"\W", "", w).isupper()) else w.lower() for w in ws)
    y1, y2 = C["small_y"], C["key_y"]
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Small,{C['small_font']},{C['small_size']},{hex2ass(C['small_color'])},&H000000FF,&H00000000,&H64000000,{1 if C.get('small_bold') else 0},0,0,0,100,100,-2,0,1,1.5,3,5,40,40,0,1
Style: Key,{C['key_font']},{C['key_size']},{hex2ass(C['key_color'])},&H000000FF,&H00101010,&H64000000,0,0,0,0,100,100,1,0,1,2,4,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for ci, c in enumerate(chunks):
        a_ = c[0][0]; nxt = chunks[ci+1][0][0] if ci + 1 < len(chunks) else c[-1][1] + 0.3
        b_ = min(max(c[-1][1] + 0.1, a_ + 0.4), nxt)
        if not any(strong(x[2]) for x in c):
            ev.append(f"Dialogue: 0,{T(a_)},{T(b_)},Small,,0,0,0,,{{\\pos(540,{(y1+y2)//2})\\fs{int(C['small_size']*1.15)}\\fad(60,0)}}{low([x[2] for x in c]).rstrip('.?!')}")
            continue
        k = len(c) - 1
        if not strong(c[k][2]):
            st = [i for i in range(len(c)) if strong(c[i][2])]
            if st and st[-1] >= len(c) - 2: k = st[-1]
        small = low([x[2] for x in c[:k]]).rstrip(".?!"); key = " ".join(x[2] for x in c[k:]).upper().rstrip(".?!,")
        fs = C["key_size"] if len(key) <= 10 else (int(C["key_size"]*0.81) if len(key) <= 14 else int(C["key_size"]*0.67))
        if small: ev.append(f"Dialogue: 0,{T(a_)},{T(b_)},Small,,0,0,0,,{{\\pos(540,{y1})\\fad(80,0)}}{small}")
        ev.append(f"Dialogue: 0,{T(a_)},{T(b_)},Key,,0,0,0,,{{\\pos(540,{y2})\\fs{fs}\\fscx115\\fscy115\\t(0,110,\\fscx100\\fscy100)}}{key}")
    open(out, "w").write((hdr + "\n".join(ev) + "\n").replace(" %", "%"))

def captions_bold(words, cfg, out):
    C = cfg["captions"]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or (w[2][-1] in ".?!" and len(cur) >= 2) or len(" ".join(x[2] for x in cur)) > 16: chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,92,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hi = hex2ass(C["key_color"]); ev = []
    for ci, c in enumerate(chunks):
        nxt = chunks[ci+1][0][0] if ci + 1 < len(chunks) else 1e9
        for i, w in enumerate(c):
            a_ = w[0]; b_ = c[i+1][0] if i + 1 < len(c) else min(c[-1][1] + 0.15, nxt)
            txt = " ".join((f"{{\\c{hi}}}" + re.sub(r"[,;]", "", x[2]).upper() + "{\\c&H00FFFFFF&}") if j == i else re.sub(r"[,;]", "", x[2]).upper() for j, x in enumerate(c))
            ev.append(f"Dialogue: 0,{T(a_)},{T(max(b_, a_+0.05))},Cap,,0,0,0,,{{\\pos(540,{C['key_y']})}}{txt}")
    open(out, "w").write(hdr + "\n".join(ev) + "\n")

def captions_quiet(words, cfg, out):
    """reference style (Oct 30 2026): 1-3 small white words on one line, low on the video; the headline does the shouting"""
    C = cfg["captions"]; Q = C.get("quiet", {})
    size, y, font = Q.get("size", 62), Q.get("y", 1330), Q.get("font", "Inter SemiBold")
    chunks, cur = [], []
    for w in words:
        if cur and (w[0] - cur[-1][1] > 0.6 or len(cur) >= 3 or len(" ".join(x[2] for x in cur + [w])) > 20): chunks.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!]$", w[2]): chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Quiet,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2.5,4,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for ci, c in enumerate(chunks):
        nxt = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else c[-1][1] + 0.4
        a_, b_ = c[0][0], min(nxt, c[-1][1] + 0.5)
        txt = " ".join(re.sub(r"[,;.]+$", "", x[2]) for x in c)   # keep natural case: AI, LinkedIn, ChatGPT, Claude, TBM stay right
        ev.append(f"Dialogue: 0,{T(a_)},{T(max(b_, a_ + 0.3))},Quiet,,0,0,0,,{{\\pos(540,{y})\\fad(60,0)}}{txt}")
    open(out, "w").write(hdr + "\n".join(ev) + "\n")

def fit_ass(path, maxw=980):
    """measure every caption line with its real font; shrink (to 75%) then split onto two lines so nothing leaves the 1080px frame"""
    import glob as _g
    try: from PIL import ImageFont
    except Exception: return
    t = open(path).read(); st = {}; cache = {}
    for m in re.finditer(r"^Style: ([^,]+),([^,]+),(\d+),(?:[^,]*,){8}(\d+),", t, re.M): st[m[1]] = (m[2], int(m[3]), int(m[4]) / 100)
    def F(name, size):
        k = (name, size)
        if k not in cache:
            key = name.replace(" ", "").lower(); fs = _g.glob("/System/Library/Fonts/**/*.tt*", recursive=True) + _g.glob("/Library/Fonts/*") + _g.glob(os.path.expanduser("~/Library/Fonts/*")) + _g.glob(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "*.tt*")) + _g.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "*.tt*"))
            c = [f for f in fs if key in os.path.basename(f).replace(" ", "").replace("-", "").lower()]
            cache[k] = ImageFont.truetype(c[0], size) if c else None
        return cache[k]
    def fix(m):
        head, style, txt = m[1], m[2], m[3]
        if style not in st: return m[0]
        fn, sz, sx = st[style]; fo = re.findall(r"\\fs(\d+)", txt); sz = int(fo[0]) if fo else sz
        po = re.findall(r"\\fscx(\d+)", txt); sx = max([sx] + [int(v) / 100 for v in po]); f = F(fn, sz)
        plain = re.sub(r"\{[^}]*\}", "", txt)
        if not f or not plain.strip(): return m[0]
        w = max(f.getlength(x) for x in plain.split("\\N")) * sx
        if w <= maxw: return m[0]
        ws = plain.split()
        if "\\N" not in plain and len(ws) >= 2 and maxw / w < (0.6 if style == "Small" else 0.75):   # the small line shrinks rather than stacking into the keyword
            half = len(ws) // 2; lines = [" ".join(ws[:half]), " ".join(ws[half:])]
            w = max(f.getlength(x) for x in lines) * sx; body = "\\N".join(lines)
            tags = "".join(re.findall(r"^\{[^}]*\}", txt))
        else:
            body = re.sub(r"^\{[^}]*\}", "", txt); tags = "".join(re.findall(r"^\{[^}]*\}", txt))
        tags = re.sub(r"\\t\([^)]*fsc[^)]*\)|\\fsc[xy]\d+", "", tags).replace("{}", "")   # drop scale pops that would grow it past the edge
        r = min(1.0, maxw / w)
        sc = "{\\fscx%d\\fscy%d}" % (int(r * sx * 100), int(r * 100)) if r < 1 else ""
        return head + tags + sc + body
    t = re.sub(r"^(Dialogue: [^,]*,[^,]*,[^,]*,([^,]+),(?:[^,]*,){5})(.*)$", fix, t, flags=re.M)
    open(path, "w").write(t)

def write_captions(words, cfg, out):
    st = cfg["captions"]["style"]
    (captions_quiet if st == "quiet" else captions_bold if st == "bold" else captions_brand)(words, cfg, out)
    fit_ass(out)

def endcard_ass(cfg, out):
    C, A = cfg["captions"], cfg["cta"]
    arrow = "".join(f"Dialogue: 0,{T(0.4+0.5*i)},{T(min(0.9+0.5*i, A['seconds']))},Arrow,,0,0,0,,{{\\move(540,{1250 if i%2==0 else 1330},540,{1330 if i%2==0 else 1250})}}▼\n" for i in range(int((A['seconds']-0.4)/0.5)+1))
    open(out, "w").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Top,{C['small_font']},76,{hex2ass(C['small_color'])},&H000000FF,&H00000000,&H80000000,{1 if C.get('small_bold') else 0},0,0,0,100,100,0,0,1,4,3,5,60,60,0,1
Style: Big,{C['key_font']},150,{hex2ass(C['key_color'])},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,5,3,5,60,60,0,1
Style: Arrow,Arial Black,200,{hex2ass(C['key_color'])},&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{T(0)},{T(A['seconds'])},Top,,0,0,0,,{{\\pos(540,700)\\fad(200,0)}}{A['line1']}
Dialogue: 0,{T(0.15)},{T(A['seconds'])},Big,,0,0,0,,{{\\pos(540,930)\\fad(200,0)\\fscx80\\fscy80\\t(0,220,\\fscx100\\fscy100)}}{A['line2'].replace('|', chr(92) + 'N')}
{arrow}""")

# ---------------------------------------------------------------- build one clip
# ---------------------------------------------------------------- top headline + soft shade
def wrap(text, n):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n: lines.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])

def headline_ass(text, cfg, dur, out):
    """clip "headline" -> top text for the whole reel (or headline.seconds). "|" = a hand-placed line break, *word* = brand colour"""
    H = cfg["headline"]; hi = hex2ass(cfg["captions"]["key_color"])
    if H.get("uppercase"): text = text.upper()
    lines = ([l.strip() for l in text.split("|")] if "|" in text else wrap(text, H["max_chars"]))[:3]
    txt = re.sub(r"\*([^*]+)\*", lambda m: f"{{\\c{hi}}}{m.group(1)}{{\\c&H00FFFFFF&}}", "\\N".join(lines))
    end = min(dur, H["seconds"]) if H.get("seconds") else dur + 1
    open(out, "w").write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Headline,{H['font']},{H['size']},&H00FFFFFF,&H000000FF,&H00000000,&H78000000,{1 if H.get('bold') else 0},0,0,0,100,100,0,0,1,{H.get('outline', 3)},{H.get('shadow', 5)},8,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,{T(0)},{T(end)},Headline,,0,0,0,,{{\\an8\\pos(540,{H['y']})\\fad(120,0)}}{txt}
""")
    fit_ass(out)

def shade_png():
    """soft dark gradient, top and bottom, laid UNDER the headline and captions so they read on bright footage"""
    p = os.path.join(os.path.expanduser("~/.tbm-video-work"), "shade.png")
    if not os.path.exists(p):
        ff("-f", "lavfi", "-i", "color=black:s=1080x1920,format=rgba", "-vf",
           "geq=r=0:g=0:b=0:a='150*max(0\\,1-Y/720)+150*max(0\\,(Y-1250)/670)'", "-frames:v", "1", p)
    return p

def text_layers(clip, cfg, wd, dur, ass):
    """extra inputs + filter chain for [0:v]: optional shade, captions, optional headline"""
    ins, chain = [], "[0:v]"
    if clip.get("headline") and cfg["headline"].get("shade", True) or cfg.get("shade"):
        ins = ["-i", shade_png()]; chain = "[0:v][1:v]overlay=0:0,"
    chain += subs(ass)
    if clip.get("headline"):
        hass = os.path.join(wd, "headline.ass"); headline_ass(clip["headline"], cfg, dur, hass); chain += "," + subs(hass)
    return ins, chain

def keep_ranges(dur, cuts):
    keep, t = [], 0.0
    for a_, b_ in sorted(cuts):
        a_, b_ = max(0, a_), min(dur, b_)
        if a_ - t > 0.05: keep.append([t, a_])
        t = max(t, b_)
    if dur - t > 0.05: keep.append([t, dur])
    return keep

def cut_video(src, keep, out, fps):
    keep = [[round(a_*fps)/fps, round(b_*fps)/fps] for a_, b_ in keep]
    fc, cat = "", ""
    for i, (a_, b_) in enumerate(keep):
        fc += (f"[0:v]trim={a_:.4f}:{b_:.4f},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={a_:.4f}:{b_:.4f},asetpts=PTS-STARTPTS,"
               f"afade=t=in:d=0.02,afade=t=out:st={max(0,b_-a_-0.03):.4f}:d=0.03[a{i}];")
        cat += f"[v{i}][a{i}]"
    fc += f"{cat}concat=n={len(keep)}:v=1:a=1[v][a]"
    ff("-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out)
    return keep

def map_time(t, keep):
    acc = 0
    for a_, b_ in keep:
        if a_ <= t <= b_: return t - a_ + acc
        acc += b_ - a_
    return None

def build_clip(P, clip, cfg):
    n = clip["name"]; src = SRC(P); wd = os.path.join(WORK(P), n); os.makedirs(wd, exist_ok=True)
    sw, shh, sfps, sdur = probe(src)
    F = min(30, round(sfps)) or 30
    S = snap(clip["start"], F); E = clip["end"]; D = E - S
    rel = lambda t: t - S
    # 1. mezzanine: one decode, frame 0 = clip start (analysis and render share frame numbers exactly)
    mezz = os.path.join(wd, "mezz.mp4")
    if not os.path.exists(mezz):
        vf = f"fps={F}" + (",scale=-2:2160" if shh > 2160 and shh <= sw else "")
        ff("-ss", f"{S:.4f}", "-t", f"{D:.4f}", "-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-g", str(F),
           "-c:a", "aac", "-b:a", "256k", mezz)
    # 2. shots
    shots_p = os.path.join(wd, "shots.json")
    shots = load_json(shots_p) or classify(mezz, cfg); json.dump(shots, open(shots_p, "w"))
    while len(shots) > 1 and shots[-1][1] - shots[-1][0] < F // 2: shots = shots[:-1]   # drop flash shot at end
    # 3. words (mezz timeline = final video timeline)
    wav = os.path.join(wd, "clip.wav"); ff("-i", mezz, "-vn", "-ac", "1", "-ar", "16000", wav)
    words = words_from(whisper(wav, wd, cfg))
    cuts = [[rel(a_), rel(b_)] for a_, b_ in clip.get("cuts", [])]
    gap = clip.get("tighten_gaps", cfg.get("tighten_gaps"))
    if gap:
        for x, y in zip(words, words[1:]):
            if y[0] - x[1] > gap: cuts.append([x[1] + 0.15, y[0] - 0.12])
    words = apply_fixes(words, {**cfg.get("fixes", {}), **clip.get("fixes", {})})
    # 4. vertical render: eye line locked, punch-ins at phrase starts and at every cut
    full = os.path.join(wd, "vertical.mp4")
    broll = [[rel(b[0]), rel(b[1]), b[2]] for b in clip.get("broll", [])]
    uncovered = render_vertical(mezz, shots, full, broll, cfg, words, [c for ab in cuts for c in ab])
    dur = probe(full)[3]
    # 5. cut out host lines, retakes, long pauses
    keep = keep_ranges(dur, cuts)
    cut = os.path.join(wd, "cut.mp4"); keep = cut_video(full, keep, cut, F)
    json.dump(keep, open(os.path.join(wd, "keep.json"), "w"))
    words_k = remap(words, keep)
    ass = os.path.join(wd, "captions.ass"); write_captions(words_k, cfg, ass)
    # 6. reel
    sp = cfg.get("speed", 1.0); od = os.path.join(P, "out", "reels"); os.makedirs(od, exist_ok=True)
    reel = os.path.join(od, f"{n}.mp4")
    at = f"atempo={sp}" if sp <= 2 else "atempo=2.0"
    ins, chain = text_layers(clip, cfg, wd, probe(cut)[3], ass)
    ff("-i", cut, *ins, "-filter_complex", f"{chain},setpts=PTS/{sp},fps=30[v];[0:a]{at}[a]", "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
       "-movflags", "+faststart", reel)
    report = {"clip": n, "reel": reel, "seconds": round(probe(reel)[3], 1), "other_speaker_shots_not_covered": uncovered}
    # 7. ad
    if clip.get("ad"):
        report["ad"] = build_ad(P, clip, cfg, wd, cut, words_k, keep, rel, sp, F)
    print(json.dumps(report))
    return report

def build_ad(P, clip, cfg, wd, cut, words_k, keep, rel, sp, F):
    n = clip["name"]; parts = []
    if clip.get("cold_open"):
        snap = lambda t, fwd: map_time(t, keep) if map_time(t, keep) is not None else \
            map_time(min([k[0] for k in keep if k[0] > t], default=t) if fwd else max([k[1] for k in keep if k[1] < t], default=t), keep)
        a_ = snap(rel(clip["cold_open"][0]), True); b_ = snap(rel(clip["cold_open"][1]), False)   # edges in a trimmed pause snap inward
        if a_ is None or b_ is None: raise SystemExit(f"{n}: cold_open falls inside a cut")
        cw = [[x - a_, y - a_, t] for x, y, t in words_k if x >= a_ - 0.02 and y <= b_ + 0.05]
        cass = os.path.join(wd, "cold.ass"); write_captions(cw, cfg, cass)
        cold = os.path.join(wd, "ad_cold.mp4")
        ff("-ss", f"{a_:.3f}", "-t", f"{b_-a_:.3f}", "-i", cut, "-vf", subs(cass), "-af", f"afade=t=out:st={max(0,b_-a_-0.08):.3f}:d=0.08",
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", cold)
        parts.append(cold)
    body = os.path.join(wd, "ad_body.mp4")
    ins, chain = text_layers(clip, cfg, wd, probe(cut)[3], os.path.join(wd, "captions.ass"))
    ff("-i", cut, *ins, "-filter_complex", chain + "[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", body)
    parts.append(body)
    seq = os.path.join(wd, "ad_seq.mp4")
    ins = []; fc = ""
    for i, p in enumerate(parts): ins += ["-i", p]; fc += f"[{i}:v][{i}:a]"
    ff(*ins, "-filter_complex", f"{fc}concat=n={len(parts)}:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
       "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", seq)
    fast = os.path.join(wd, "ad_fast.mp4")
    ff("-i", seq, "-filter_complex", f"[0:v]setpts=PTS/{sp},fps=30[v];[0:a]atempo={sp}[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
       "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", fast)
    last = os.path.join(wd, "last.png"); ff("-sseof", "-0.2", "-i", cut, "-frames:v", "1", "-update", "1", last)   # clean frame, no captions
    eass = os.path.join(wd, "endcard.ass"); endcard_ass(cfg, eass); secs = cfg["cta"]["seconds"]
    end = os.path.join(wd, "ad_end.mp4")
    ff("-loop", "1", "-t", str(secs), "-i", last, "-f", "lavfi", "-t", str(secs), "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex",
       f"[0:v]scale=1080:1920,boxblur=24:2,eq=brightness=-0.25,fps=30,{subs(eass)},format=yuv420p[v]", "-map", "[v]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", end)
    od = os.path.join(P, "out", "ads"); os.makedirs(od, exist_ok=True); ad = os.path.join(od, f"AD_{n}.mp4")
    ff("-i", fast, "-i", end, "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
       "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", ad)
    return ad

def cmd_build(a):
    P = a.project; cfg = cfg_of(P); clips = clips_of(P)
    todo = clips if a.clip == "all" else [c for c in clips if c["name"] == a.clip]
    if not todo: raise SystemExit("no such clip in clips.json")
    for c in todo:
        if a.fresh: shutil.rmtree(os.path.join(WORK(P), c["name"]), ignore_errors=True)
        build_clip(P, c, cfg)

# ---------------------------------------------------------------- words helper
INTER = re.compile(r"^(exactly|okay|ok|yes|yeah|amazing|right|wow|great|so true|very good|sure|nice|hmm|absolutely|correct|true)[.!?, ]*$", re.I)
def cmd_words(a):
    """accurate words for one clip (small model), absolute times, likely host interjections flagged"""
    P = a.project; cfg = cfg_of(P)
    clip = [c for c in clips_of(P) if c["name"] == a.clip][0]
    wd = os.path.join(WORK(P), clip["name"]); os.makedirs(wd, exist_ok=True)
    s0 = max(0, clip["start"] - 0.5)
    wav = os.path.join(wd, "words_src.wav")
    ff("-ss", f"{s0:.3f}", "-to", f"{clip['end'] + 0.5:.3f}", "-i", SRC(P), "-vn", "-ac", "1", "-ar", "16000", wav)
    w = words_from(whisper(wav, wd, cfg))
    prev_end = None
    for x in w:
        gap = f"   [pause {x[0]-prev_end:.1f}s]" if prev_end is not None and x[0] - prev_end > 0.5 else ""
        flag = "  <== host?" if INTER.match(x[2]) else ""
        print(f"{x[0]+s0:8.2f}-{x[1]+s0:8.2f}  {x[2]}{flag}{gap}")
        prev_end = x[1]

# ---------------------------------------------------------------- checks
def glitch_frames(p):
    cv2, np = _cv()
    f = read_frames(p, 108, 192, color=False).astype(float)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    return [i for i in range(1, len(f) - 1) if d[i-1] > 20 and d[i] > 20]

def face_under_text(p, cfg):
    cv2, np = _cv()
    fr = read_frames(p, 540, 960, fps=2, color=False)
    top = cfg["captions"]["small_y"] - 60
    bad = []
    for i, f in enumerate(fr):
        for x, y, w, h in faces_in(f, 60):
            if (y + h) * 2 > top and w > 90: bad.append(i / 2)   # only big faces: small detections are hands/mic
    return bad

def eye_line(p, cfg):
    """median eye height and how far it wanders (px on 1920 tall frame); the editor's rule: eyes stay on one line"""
    cv2, np = _cv()
    fr = read_frames(p, 540, 960, fps=3, color=False)
    ys = []
    for f in fr:
        fs = [x for x in faces_in(f, 70) if x[2] > 110]
        if fs: x, y, w, h = fs[0]; ys.append((y + 0.38 * h) * 2)
    if not ys: return None
    ys = np.array(ys); med = float(np.median(ys))
    return {"eye_y_median": round(med), "frames_off_line_over_60px": int((np.abs(ys - med) > 60).sum()), "frames_measured": len(ys)}

def cmd_check(a):
    P = a.project; cfg = cfg_of(P); clips = clips_of(P)
    names = [c["name"] for c in clips] if a.clip in (None, "all") else [a.clip]
    cd = os.path.join(P, "out", "checks"); os.makedirs(cd, exist_ok=True)
    host = [h.lower() for h in cfg.get("host_phrases", [])] + ["exactly", "wow", "amazing", "so true"]
    report = []
    for n in names:
        for kind, p in (("reel", os.path.join(P, "out", "reels", f"{n}.mp4")), ("ad", os.path.join(P, "out", "ads", f"AD_{n}.mp4"))):
            if not os.path.exists(p): continue
            r = {"file": os.path.relpath(p, P), "glitch_frames": glitch_frames(p), "face_under_text_sec": face_under_text(p, cfg), "eye_line": eye_line(p, cfg)}
            wav = os.path.join(cd, f"{kind}_{n}.wav"); ff("-i", p, "-vn", "-ac", "1", "-ar", "16000", wav)
            js = whisper(wav, cd, cfg, words=False)
            text = " ".join(s["text"] for s in json.load(open(js))["segments"])
            r["host_words_found"] = [h for h in host if re.search(r"\b" + re.escape(h) + r"\b", text.lower())]
            # a faint off-mic "Exactly" can be missed by the fresh transcript but still sit in the captions: scan them too
            for an in ("captions_pro.ass", "captions.ass"):
                ap_ = os.path.join(WORK(P), n, an)
                if os.path.exists(ap_):
                    for ln in open(ap_):
                        if ln.startswith("Dialogue: 0,"):
                            t_ = re.sub(r"\{[^}]*\}", "", ln.split(",,", 1)[-1].split(",", 4)[-1]).strip()
                            if INTER.match(t_): r["host_words_found"].append(f"caption '{t_}' at {ln.split(',')[1]}")
                    break
            r["transcript"] = text.strip()
            d = probe(p)[3]
            ff("-i", p, "-vf", f"fps=12/{d:.2f},scale=180:320,tile=6x2", "-frames:v", "1", os.path.join(cd, f"{kind}_{n}_sheet.jpg"))
            report.append(r)
            flag = "OK" if not (r["glitch_frames"] or r["host_words_found"]) else "CHECK"
            print(f"[{flag}] {r['file']}: glitches={r['glitch_frames']} host_words={r['host_words_found']} face_near_text={r['face_under_text_sec'][:6]} eye_line={r['eye_line']}")
    json.dump(report, open(os.path.join(cd, "report.json"), "w"), indent=1)
    print("contact sheets + transcripts in", cd, "- LOOK at every sheet before delivering")

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("command"); ap.add_argument("arg", nargs="?")
    ap.add_argument("--project", default="."); ap.add_argument("--times"); ap.add_argument("--time", type=float); ap.add_argument("--face", type=int)
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args(); a.project = os.path.abspath(os.path.expanduser(a.project))
    c = a.command
    if c == "check-setup": cmd_check_setup(a)
    elif c == "fetch": a.src = a.arg; cmd_fetch(a)
    elif c == "transcribe": cmd_transcribe(a)
    elif c == "probe": cmd_probe(a)
    elif c == "set-speaker": cmd_set_speaker(a)
    elif c == "words": a.clip = a.arg; cmd_words(a)
    elif c == "build": a.clip = a.arg or "all"; cmd_build(a)
    elif c == "check": a.clip = a.arg; cmd_check(a)
    else: raise SystemExit(__doc__)

if __name__ == "__main__":
    main()
