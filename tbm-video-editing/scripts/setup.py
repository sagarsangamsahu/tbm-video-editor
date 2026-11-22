"""One-time setup for the TBM video editing skill, on Mac or Windows.

Mac:      python3 <skill-dir>/scripts/setup.py
Windows:  py -3.12 <skill-dir>/scripts/setup.py   (or: python <skill-dir>/scripts/setup.py)

Installs ffmpeg (Homebrew on Mac, winget on Windows), then makes ~/.tbm-video-work/.venv with
opencv, numpy, pillow, yt-dlp and openai-whisper, and ends with tbm.py check-setup (must print READY).
"""
import glob, os, shutil, subprocess, sys

WIN = os.name == "nt"
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.expanduser("~/.tbm-video-work")
V = os.path.join(WORK, ".venv")
VPY = os.path.join(V, "Scripts", "python.exe") if WIN else os.path.join(V, "bin", "python")

def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kw)

def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p: return os.path.dirname(p)
    if WIN:   # winget puts it on PATH only for NEW terminals, so look where it lands
        la = os.environ.get("LOCALAPPDATA", "")
        for pat in [os.path.join(la, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
                    os.path.join(la, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin", "ffmpeg.exe"),
                    r"C:\ffmpeg\bin\ffmpeg.exe"]:
            hit = glob.glob(pat, recursive=True)
            if hit: return os.path.dirname(hit[0])
    else:
        for d in ["/opt/homebrew/bin", "/usr/local/bin"]:
            if os.path.exists(os.path.join(d, "ffmpeg")): return d
    return None

def base_python():
    """torch (needed by whisper) has wheels for Python 3.9-3.13: prefer one of those for the venv"""
    if WIN and shutil.which("py"):
        for v in ["3.12", "3.11", "3.13", "3.10"]:
            if run(["py", f"-{v}", "-c", "pass"], capture_output=True).returncode == 0: return ["py", f"-{v}"]
    for v in ["3.12", "3.11", "3.13", "3.10"]:
        p = shutil.which(f"python{v}")
        if p: return [p]
    return [sys.executable]

def main():
    os.makedirs(WORK, exist_ok=True)
    fd = find_ffmpeg()
    if not fd:
        if WIN:
            run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"])
        elif shutil.which("brew") or os.path.exists("/opt/homebrew/bin/brew"):
            run([shutil.which("brew") or "/opt/homebrew/bin/brew", "install", "ffmpeg"], check=True)
        else:
            sys.exit("NOT READY: Homebrew is missing. Open the Terminal app, paste the install line from https://brew.sh, "
                     "enter your laptop password when asked, then run this setup again.")
        fd = find_ffmpeg()
        if not fd: sys.exit("NOT READY: ffmpeg did not install. Close Claude, open it again, and run the setup again.")
    open(os.path.join(WORK, "ffmpeg_dir.txt"), "w").write(fd)   # tbm.py adds this folder to PATH

    if not os.path.exists(VPY):
        run(base_python() + ["-m", "venv", V], check=True)
    run([VPY, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    run([VPY, "-m", "pip", "install", "-q", "opencv-python-headless<5", "numpy", "pillow", "yt-dlp", "openai-whisper"], check=True)
    r = run([VPY, os.path.join(D, "scripts", "tbm.py"), "check-setup"])
    sys.exit(r.returncode)

if __name__ == "__main__":
    main()
