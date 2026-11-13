#!/usr/bin/env python3
"""Assemble a vertical "What If" Short from an episode folder.

Episode folder layout:
  episode.json   title, top_text, highlight, shots[] (see episodes/ep01-friction)
  voice.mp3      narration
  words.json     [{"word": "If", "start": 0.12, "end": 0.30}, ...]  word timings
  music.mp3      optional background music
  shots/         one image (.png/.jpg) or clip (.mp4) per shot

Each shot has a "cue": the first spoken words of that shot. Shot start times
come from where the cue is spoken, so cuts always land on the narration.

Usage: python3 pipeline/build.py episodes/ep01-friction
Output: <episode>/out/final.mp4  (1080x1920, 30 fps, -14 LUFS)
"""
import json, re, subprocess, sys, shutil
from pathlib import Path

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
MOTIONS = ["push_in", "pan_right", "pull_out", "pan_left"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def align_shots(shots, words, total):
    """Give every shot a start/end from where its cue is spoken."""
    toks = [norm(w["word"]) for w in words]
    pos = 0
    for i, s in enumerate(shots):
        if i == 0:
            s["start"] = 0.0
            continue
        cue = [norm(c) for c in s["cue"].split() if norm(c)]
        for j in range(pos, len(toks) - len(cue) + 1):
            if toks[j:j + len(cue)] == cue:
                s["start"] = max(0.0, words[j]["start"] - 0.08)
                pos = j + 1
                break
        else:
            sys.exit(f"Cue not found in narration: shot {i + 1} '{s['cue']}'")
    for i, s in enumerate(shots):
        s["end"] = shots[i + 1]["start"] if i + 1 < len(shots) else total
    return shots


def render_shot(src, dur, motion, out):
    """Make one 1080x1920 segment of exact length, with gentle camera motion."""
    frames = max(1, round(dur * FPS))
    if src.suffix.lower() in (".mp4", ".mov", ".webm"):
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"fps={FPS},tpad=stop_mode=clone:stop_duration={dur},setsar=1")
        run(["ffmpeg", "-y", "-i", src, "-an", "-vf", vf, "-frames:v", str(frames),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])
        return
    z = 0.12  # total zoom over the shot
    zexpr = {"push_in": f"1+{z}*on/{frames}", "pull_out": f"1+{z}-{z}*on/{frames}"}.get(motion, f"1+{z}")
    if motion == "pan_right":
        x = f"(iw-iw/zoom)*on/{frames}"
    elif motion == "pan_left":
        x = f"(iw-iw/zoom)*(1-on/{frames})"
    else:
        x = "iw/2-(iw/zoom/2)"
    # Upscale 4x before zoompan so the motion is smooth, not jittery.
    vf = (f"scale={W * 4}:{H * 4}:force_original_aspect_ratio=increase,crop={W * 4}:{H * 4},"
          f"zoompan=z='{zexpr}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-loop", "1", "-i", src, "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out])


def ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def build_ass(ep, shots, words, out):
    """Word-by-word captions, the opening top text, and stat badges."""
    YEL, WHITE = "&H003FD2FF", "&H00FFFFFF"  # ASS colours are BGR
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat Black,104,{WHITE},{WHITE},&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,9,4,2,60,60,560,1
Style: Top,Montserrat Black,82,{WHITE},{WHITE},&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,3,8,70,70,230,1
Style: Badge,Montserrat Black,70,&H002B1A14,&H002B1A14,{YEL},{YEL},1,0,0,0,100,100,2,0,3,22,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    # Opening top text, highlighted word in yellow, for the first shot.
    top = ep["top_text"].upper()
    hl = ep.get("highlight", "").upper()
    if hl:
        top = top.replace(hl, f"{{\\c{YEL}}}{hl}{{\\c{WHITE}}}", 1)
    ev.append(f"Dialogue: 1,{ts(0)},{ts(shots[0]['end'])},Top,,0,0,0,,{{\\fad(0,200)}}{top}")
    # Stat badges pop in 0.25s after the shot starts.
    for s in shots:
        if s.get("badge"):
            st = s["start"] + 0.25
            pop = r"{\pos(540,900)\fscx40\fscy40\t(0,140,\fscx112\fscy112)\t(140,240,\fscx100\fscy100)\fad(0,120)}"
            ev.append(f"Dialogue: 2,{ts(st)},{ts(s['end'] - 0.05)},Badge,,0,0,0,,{pop}{s['badge']}")
    # Captions: groups of up to 3 words, never across a sentence end or a cut.
    cuts = {round(s["start"], 2) for s in shots}
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) == 3 or re.search(r"[.?!…]$", cur[-1]["word"])
                    or any(cur[-1]["end"] <= c <= w["start"] + 0.01 for c in cuts)
                    or w["start"] - cur[-1]["end"] > 0.45):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"] + 0.3
        g_end = min(g_end, g[-1]["end"] + 0.6)
        for k, w in enumerate(g):
            a = w["start"]
            b = g[k + 1]["start"] if k + 1 < len(g) else g_end
            txt = []
            for m, x in enumerate(g):
                word = re.sub(r"[^\w'%★☆-]", "", x["word"]).upper()
                txt.append(f"{{\\c{YEL}}}{word}{{\\c{WHITE}}}" if m == k else word)
            ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{' '.join(txt)}")
    Path(out).write_text(head + "\n".join(ev) + "\n")


def make_sfx(tmp, total, shots):
    """Synthesised whoosh on every cut and a low hit on every badge."""
    whoosh = tmp / "whoosh.wav"
    hit = tmp / "hit.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:a=0.6",
         "-af", "highpass=f=400,lowpass=f=5000,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25,volume=0.5", whoosh])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=55:d=0.6",
         "-af", "afade=t=out:st=0.05:d=0.55,volume=1.4", hit])
    inputs, filt, labels = [], [], []
    idx = 0
    for s in shots[1:]:
        inputs += ["-i", str(whoosh)]
        d = int(max(0, s["start"] - 0.15) * 1000)
        filt.append(f"[{idx}]adelay={d}|{d}[w{idx}]"); labels.append(f"[w{idx}]"); idx += 1
    for s in shots:
        if s.get("badge"):
            inputs += ["-i", str(hit)]
            d = int((s["start"] + 0.25) * 1000)
            filt.append(f"[{idx}]adelay={d}|{d}[w{idx}]"); labels.append(f"[w{idx}]"); idx += 1
    out = tmp / "sfx.wav"
    if not labels:
        return None
    fc = ";".join(filt) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad=whole_dur={total}[o]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[o]", "-t", str(total), out])
    return out


def main(ep_dir):
    ep_dir = Path(ep_dir).resolve()
    ep = json.loads((ep_dir / "episode.json").read_text())
    words = json.loads((ep_dir / "words.json").read_text())
    voice = ep_dir / "voice.mp3"
    total = round(duration(voice) + 0.6, 2)
    shots = align_shots(ep["shots"], words, total)
    tmp = ep_dir / "out" / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    segs = []
    for i, s in enumerate(shots):
        src = ep_dir / s["media"]
        if not src.exists():
            src = ROOT / ep.get("placeholder", "assets/mascot/mascot-A-refsheet.png")
        seg = tmp / f"seg{i:02d}.mp4"
        render_shot(src, s["end"] - s["start"], s.get("motion", MOTIONS[i % 4]), seg)
        segs.append(seg)
        print(f"shot {i + 1:2d}  {s['start']:5.2f}-{s['end']:5.2f}s  {s.get('badge') or ''}")
    (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in segs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", tmp / "list.txt", "-c", "copy", tmp / "video.mp4"])

    build_ass(ep, shots, words, tmp / "captions.ass")
    sfx = make_sfx(tmp, total, shots)

    # Mix: voice on top, music ducked under the voice, sfx; then loudness to -14 LUFS.
    cmd = ["ffmpeg", "-y", "-i", tmp / "video.mp4", "-i", voice]
    chains = ["[1:a]apad=whole_dur=%s,volume=1.0[v]" % total]
    mix = ["[v]"]
    n = 2
    music = ep_dir / "music.mp3"
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", music]
        chains.append(f"[{n}:a]atrim=0:{total},volume=0.35,afade=t=out:st={total - 1.2}:d=1.2[m0]")
        chains.append("[v]asplit[v][vk]")
        chains.append("[m0][vk]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[m]")
        mix.append("[m]"); n += 1
    if sfx:
        cmd += ["-i", sfx]
        chains.append(f"[{n}:a]volume=0.8[s]"); mix.append("[s]"); n += 1
    chains.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0,loudnorm=I=-12.5:TP=-1.5:LRA=11[a]")
    out = ep_dir / "out" / "final.mp4"
    cmd += ["-filter_complex", ";".join(chains),
            "-vf", f"ass={tmp / 'captions.ass'}:fontsdir={FONTS}",
            "-map", "0:v", "-map", "[a]", "-t", str(total),
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    run(cmd)
    print(f"\nDone: {out}  ({duration(out):.1f}s)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "episodes/ep01-friction")
