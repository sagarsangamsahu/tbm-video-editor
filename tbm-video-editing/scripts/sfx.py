"""Add optional sound effects (and music) to a finished reel. Default is none: run this only when the person asked.
  python tools/sfx.py out/reel.mp4 light            pop on the hook headline, soft hit on the call to action
  python tools/sfx.py out/reel.mp4 full             light + a soft whoosh on cuts (never closer than 3 s apart)
  python tools/sfx.py out/reel.mp4 full --music song.mp3   also a quiet music bed that dips under the voice
Run it right after make_reel.py for that version (it reads work/cap.ass and work/keep.used.json of the last render).
The sounds are made by code (ffmpeg), so they are free for any use, ads included, with no credit needed.
Extra sounds from openverse.org: use only ones marked CC0, save them in sfx/ as pop.wav, hit.wav, whoosh.wav ... to override.
Any video works (student and team skills too): pass your own times with --at "0.1:pop,12.4:whoosh2".
Writes out/<name>-sfx.mp4 (the original stays untouched) and prints where each sound landed."""
import os, re, sys, json, argparse
try:
    from common import FF, probe, run
except ImportError:   # used on its own (student / team skills)
    import subprocess
    FF = os.environ.get('FFMPEG', 'ffmpeg')
    def run(cmd):
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if p.returncode: raise SystemExit('ffmpeg failed:\n' + p.stderr[-2500:])
        return p.stderr
    def probe(path):
        t = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, stdin=subprocess.DEVNULL).stderr
        m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', t)
        return (int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0), 0, 0, True

# name -> ffmpeg lavfi source (all mono 48 kHz, short)
PACK = {
    'pop':     "aevalsrc='0.8*sin(2*PI*(700+900*exp(-40*t))*t)*exp(-35*t)':s=48000:d=0.18",
    'pop2':    "aevalsrc='0.8*sin(2*PI*(1100+600*exp(-50*t))*t)*exp(-45*t)':s=48000:d=0.14",
    'click':   "aevalsrc='0.7*sin(2*PI*2400*t)*exp(-120*t)':s=48000:d=0.05",
    'tick':    "aevalsrc='0.6*sin(2*PI*3200*t)*exp(-200*t)':s=48000:d=0.04",
    'ding':    "aevalsrc='0.45*(sin(2*PI*1320*t)+0.6*sin(2*PI*1980*t))*exp(-6*t)':s=48000:d=0.8",
    'chime':   "aevalsrc='0.4*(sin(2*PI*1046*t)+sin(2*PI*1568*t)*exp(-3*t))*exp(-4*t)':s=48000:d=1.0",
    'hit':     "aevalsrc='0.9*sin(2*PI*(55+80*exp(-18*t))*t)*exp(-7*t)':s=48000:d=0.6",
    'boom':    "aevalsrc='0.9*sin(2*PI*(40+60*exp(-10*t))*t)*exp(-4*t)':s=48000:d=1.0",
    'thud':    "aevalsrc='0.9*sin(2*PI*(90+60*exp(-30*t))*t)*exp(-14*t)':s=48000:d=0.3",
    'whoosh':  "anoisesrc=c=pink:a=0.5:d=0.5:r=48000,bandpass=f=1400:w=1800,afade=t=in:d=0.3:curve=qsin,afade=t=out:st=0.3:d=0.2",
    'whoosh2': "anoisesrc=c=pink:a=0.5:d=0.35:r=48000,highpass=f=600,lowpass=f=5000,afade=t=in:d=0.2:curve=qsin,afade=t=out:st=0.2:d=0.15",
    'swipe':   "anoisesrc=c=white:a=0.3:d=0.25:r=48000,bandpass=f=3000:w=2500,afade=t=in:d=0.1,afade=t=out:st=0.1:d=0.15",
    'rise':    "anoisesrc=c=pink:a=0.4:d=1.2:r=48000,highpass=f=300,afade=t=in:d=1.1:curve=exp,afade=t=out:st=1.1:d=0.1",
    'sparkle': "aevalsrc='0.3*sin(2*PI*(2000+1500*t)*t)*exp(-5*t)':s=48000:d=0.5",
    'type':    "aevalsrc='0.5*sin(2*PI*1800*t)*exp(-150*t)':s=48000:d=0.03",
}
GAIN_DB = {'light': -14, 'full': -12}   # sounds sit well under the voice


def sound(name, folder):
    own = os.path.join('sfx', name + '.wav')
    if os.path.exists(own):
        return own
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, name + '.wav')
    if not os.path.exists(p):
        run([FF, '-nostdin', '-y', '-f', 'lavfi', '-i', PACK[name], '-ac', '1', '-ar', '48000', p])
    return p


def secs(t):
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('mode', choices=['none', 'light', 'full'])
    ap.add_argument('--music'); ap.add_argument('--music-db', type=float, default=-26)
    ap.add_argument('--ass', default='work/cap.ass'); ap.add_argument('--keep', default='work/keep.used.json')
    ap.add_argument('--out')
    ap.add_argument('--at', help='your own sound times, e.g. "0.1:pop,12.4:whoosh2,30.2:hit" (replaces the automatic ones)')
    a = ap.parse_args()
    if a.mode == 'none' and not a.music:
        print('mode none: nothing to add'); return
    dur = probe(a.video)[0]
    ass = open(a.ass, encoding='utf-8').read() if os.path.exists(a.ass) else ''
    ev = []   # (time, sound)
    for st, en, style in re.findall(r'^Dialogue: \d+,([^,]+),([^,]+),(Hook|CTA),', ass, re.M):
        if a.mode in ('light', 'full'):
            ev.append((secs(st) + 0.02, 'pop' if style == 'Hook' else 'hit'))
    if a.mode == 'full' and os.path.exists(a.keep):
        keep = json.load(open(a.keep)); t = 0.0; last = -9
        busy = [x[0] for x in ev]
        for s_, e_ in keep[:-1]:
            t += e_ - s_
            if t - last >= 3.0 and all(abs(t - b) > 1.0 for b in busy) and 1.0 < t < dur - 1.0:
                ev.append((t - 0.25, 'whoosh2')); last = t
    if a.at:
        ev = [(float(x.split(':')[0]), x.split(':')[1]) for x in a.at.split(',') if ':' in x]
        bad = [n for _, n in ev if n not in PACK and not os.path.exists(os.path.join('sfx', n + '.wav'))]
        if bad: raise SystemExit('unknown sound: ' + ', '.join(bad) + '. Choose from: ' + ', '.join(PACK))
    ev.sort()
    folder = os.path.join(os.path.expanduser('~'), 'asr', 'sfx')
    ins, fc, mix = ['-i', a.video], [], ['[0:a]']
    for i, (t, nm) in enumerate(ev):
        ins += ['-i', sound(nm, folder)]
        ms = max(0, int(t * 1000))
        fc.append(f'[{i+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={GAIN_DB.get(a.mode, -14)}dB,adelay={ms}|{ms}[s{i}]')
        mix.append(f'[s{i}]')
    if a.music:
        k = len(ev) + 1
        ins += ['-stream_loop', '-1', '-i', a.music]
        fc.append(f'[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={a.music_db}dB,atrim=0:{dur:.3f},'
                  f'afade=t=in:d=1,afade=t=out:st={max(0, dur-1.5):.3f}:d=1.5[mraw]')
        fc.append('[0:a]asplit[v1][v2]'); mix[0] = '[v1]'
        fc.append('[mraw][v2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus]')   # music dips under the voice
        mix.append('[mus]')
    fc.append(''.join(mix) + f'amix=inputs={len(mix)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[ao]')
    out = a.out or re.sub(r'\.mp4$', '', a.video) + '-sfx.mp4'
    run([FF, '-nostdin', '-y', *ins, '-filter_complex', ';'.join(fc), '-map', '0:v', '-map', '[ao]',
         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out])
    for t, nm in ev:
        print(f'{t:6.2f}s  {nm}')
    print(('music bed under the voice\n' if a.music else '') + 'saved ' + out)


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
