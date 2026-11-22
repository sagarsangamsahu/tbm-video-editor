---
name: tbm-video-editing
description: TBM video editing (for TBM students and anyone). Turns a long video (podcast, interview, webinar, live) or a raw talking-head recording into finished vertical reels / YouTube Shorts with brand captions, plus paid-ad versions with a cold-open hook and a workshop CTA end card, plus titles and descriptions. Use when someone shares a video file or Google Drive link and says "make reels", "cut shorts from this podcast", "edit my raw video", "make ads from this", "clip this", "TBM edit", or similar.
---

# TBM Video Editing

Long video or raw recording in → reels, Shorts and ads out. The heavy lifting is in `scripts/tbm.py`. Your job is judgment: picking moments, deciding cuts, and checking the result the way a viewer would.

`<skill-dir>` is the folder that contains this SKILL.md. It can be `~/.claude/skills/tbm-video-editing` or a project's `.claude/skills/tbm-video-editing`, e.g. inside a Google Drive project.
```
PY=~/.tbm-video-work/.venv/bin/python                 # Mac
PY=~/.tbm-video-work/.venv/Scripts/python.exe         # Windows
TBM=<skill-dir>/scripts/tbm.py
$PY $TBM <command> --project <project-folder>
```
**First use on a new laptop** (no `~/.tbm-video-work/.venv` yet), set up once. It must end with `READY`:
- **Mac:** `python3 <skill-dir>/scripts/setup.py`. If it says Homebrew is missing, tell the student, in simple words, to open the Terminal app, paste the install line from https://brew.sh and type their laptop password when asked (you cannot type passwords). Then run setup again.
- **Windows:** first check for Python with `py -3.12 --version`. If it is missing, run `winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements`. Then run `py -3.12 <skill-dir>/scripts/setup.py`, which installs ffmpeg with winget. If winget is missing, ask the student to update "App Installer" from the Microsoft Store. If `py` is still not found right after installing, ask them to close Claude, open it again, then run setup again.
- Setup downloads about 1-2 GB (Whisper speech model + tools). It takes 5-15 minutes, so keep the laptop plugged in and online.
- On Windows, quote any path with spaces. Paths may use forward slashes.
Heavy files (the downloaded source and temporary renders) are kept on the laptop in `~/.tbm-video-work/`, never in the project, so projects inside Google Drive stay light. Only finished reels, ads, checks and settings go in the project folder.

## 0. Intake: ask before working (one AskUserQuestion call, then follow-ups)
Never assume anyone's branding. Every student chooses their own look.
Do not ask what kind of video it is. Find out yourself: fetch the video, run `probe`, and look at the frames.
1. How will they give it? A YouTube link, a Google Drive link, or a file dropped into the project folder. All three work. (Usually they have already pasted it.)
2. **Only if the probe frames show 2 or more people** (podcast, interview): show them the numbered probe image and ask which person the reels should follow. If only one person appears, set `"mode": "solo"` and never ask this.
3. How many clips? What should they focus on: bold takes, emotional stories, practical tips, funny moments?
4. **Caption colour and style.** Ask for their brand colour. If they show a screenshot of their feed or logo, match it. If they don't know, offer these choices and help them pick:
   - Bright yellow `#FFE14D` (classic, readable on any video)
   - Lime green `#C6F25E` (fresh, modern)
   - Electric blue `#4DA3FF` (calm, trustworthy)
   - Hot pink `#FF4D9D` (bold, playful)
   - Orange `#FF8A3D` (energetic)
   - White only (minimal)
   Style: "brand" (small white line + big coloured keyword) or "bold" (big white words, the active word coloured).
5. **Ads?** Ask only if they asked for ads. The student writes their own CTA: line 1 small (e.g. "register for the"), line 2 big (e.g. "FREE MASTERCLASS"). Use `|` for a line break. If they are stuck, suggest 2 to 3 options based on their offer.
6. **Ads only:** what text at the top: an audience badge ("FOR COACHES & COURSE CREATORS"), a headline/title, or nothing?
7. Speed: 1.0x (natural) or 1.1x (snappier)?
8. **Reference reels?** If they have a reel they love: "Take inspiration from it, or copy the style as closely as possible?" Both are fine (see `references/pro-standards.md` section 1).
9. **Sound?** **None** (default: voice only), **Light** (soft pop when the headline appears, soft hit on the CTA) or **Full** (light plus a soft whoosh on cuts). Music: only their own track or one marked CC0; show a short preview first and keep it only if they approve.
10. **Spoken language + caption script.** English, Hindi or Hinglish? Captions in Roman ("aapko") or Devanagari? For Hindi/Hinglish set `"language": "hi"` in config.json (the scripts then switch to the multilingual Whisper models automatically; `.en` models return almost nothing on Hinglish). Whisper often writes Hinglish in Devanagari or odd spellings ("koji" for "koi"), so rewrite every caption in the script they chose before building.
11. **Key words glossary.** Ask for their name, brand, programme and tool names up front (e.g. "Claude", which Whisper hears as "cloud"). Use it to fix the captions (rule 24).
12. **Simple or heavy graphics?** Simple (captions, zooms, proof screenshots) is fast. Heavy animated graphics are much slower and use many more tokens; recommend simple unless it's one hero video.
Then **storyboard first**: show the clip list (hook + one line each) and one preview frame; build only what they approve.
Write the answers into `<project>/config.json` (see `templates/config.example.json`). Only put in what differs from `config.default.json`. Remember the student's choices for their next project.

Read `references/pro-standards.md` once per project (colour theme, readability, defaults, delivery checklist).

## 1. Get the video
`$PY $TBM fetch "<YouTube link | Drive link | file path>" --project <dir>`. YouTube links use yt-dlp. Public Google Drive links download directly. For a dropped file, pass its path. Only download videos the student owns or has rights to. For a file over 2 GB, tell the user it will take a while. If the user only wants one section of a huge Drive file, ffmpeg can stream just that section: `ffmpeg -ss START -i "<drive usercontent url>" -t DUR -c copy part.mp4`.

## Path B: one raw reel (video under ~3 minutes)
Check the length with `probe` first. Under ~3 minutes = ONE polished reel, not many clips. Never ask "how many reels?" and never show a clip list.
1. `fetch`, `transcribe`, then `words` on the whole video (one clip in `clips.json`: start 0, end = duration).
2. Clean it: cut retakes (keep the LAST clean take of each line), false starts, "umm/uh", repeated words and dead air. Set `"tighten_gaps": 0.45`. Start on the first strong sentence, end on the payoff.
3. Polish: captions in their colour, `"hook_lines"` for the first 3 s, punch-in zooms at every cut (hides jump cuts), face never covered.
4. Ask only: colour (if unknown), a reel they love (copy or inspiration), sound (none, light or full; default none) and music (default none, preview first), headline at the top (yes/no), end card + CTA (yes/no).
5. Storyboard: one preview frame + the cut list in plain words ("I'll remove the 2 retakes at 0:12 and 0:40 and the long pause at 1:05"). Build after "go".
6. Deliver one reel + a ready caption with hashtags. Run the same checks as always.

## Path A: long video -> many reels
## 2. Transcribe and pick moments
`$PY $TBM transcribe --project <dir>` writes `transcript.txt`. Read it all (in pages). Pick moments that work on their own:
- **Hook in the first sentence**: a contrarian claim ("You don't need an accountability partner"), a number ("9 webinars, zero sales"), or a vulnerable confession ("87 videos I never posted").
- **One idea per clip.** 20 to 90 seconds. Start on a complete, strong sentence, never on "so…" or a host question. End on the payoff line.
- **Mix the types**: emotional story, framework or practical tip, bold take, personal failure → turnaround.
- Never start a clip with the host asking a question. If the answer doesn't stand alone, choose another moment.
Write `<project>/clips.json` (see `templates/clips.example.json`). **All times are absolute seconds in the source.**

## 3. Main speaker (podcasts only)
`$PY $TBM probe --project <dir>` → view the `probe/*.jpg` images (numbered yellow boxes) → `$PY $TBM set-speaker --time T --face K`. This learns the main speaker's look and everyone else's, so the main speaker is followed through split screens, solo shots and wide shots. For solo videos set `"mode": "solo"` and skip this step.

## 4. Decide cuts per clip
`$PY $TBM words <clip> --project <dir>` prints accurate word timings, flags `<== host?` interjections and shows `[pause]` gaps.
- **Cut every host reaction** ("Exactly", "Okay", "Right", "Wow", "Amazing"): cut only the gap between the main speaker's words, from the end of their last word to the start of their next.
- **Cut host questions.** The clip must make sense from the speaker alone.
- **Raw videos:** cut retakes (repeated sentences: keep the last, cleanest take), false starts and filler. Set `"tighten_gaps": 0.6` to shrink every pause over 0.6s automatically.
- **Ads:** set `"ad": true` and `"cold_open": [start, end]`, the single strongest line of the clip. It plays first, then the clip, then the CTA end card.
- **Top headline** (optional, rule 22): `"headline": "I NEVER KNEW MY NICHE.|*HERE'S WHAT I POSTED*"`. It stays at the top for the whole reel (and the ad body). `|` places the line break; `*words*` turn the brand colour (`captions.key_color`); text that is too wide shrinks to fit. Look and position live in config `"headline"`: font (Impact), size 104, y 205, `"uppercase"`, `"seconds"` (null = whole reel) and `"shade": true` (a soft dark gradient under the headline and captions so they read on bright footage).
- **B-roll** (optional): `"broll": [[start, end, "/path/clip.mp4"]]`. Use it for moments that show only the other person, or to illustrate a concrete word ("webinar", "laptop"). Free stock comes from Pexels. **Always ask the user before downloading** and state the file, source and size.

## 5. Build
`$PY $TBM build <clip|all> --project <dir>` (add `--fresh` after changing speaker settings). Output goes to `out/reels/<clip>.mp4` and `out/ads/AD_<clip>.mp4`. If `other_speaker_shots_not_covered` is not empty, those seconds show the other person: cut them or add B-roll.

What the engine does: frame-exact vertical crops from the full-resolution source; the main speaker only; **the eyes locked on the same horizontal line in every shot and every zoom** (`eye_line` 0.36 from the top); consistent face size; punch-in zooms on new phrases and at every cut (this hides jump cuts); brand captions placed below the face; speed-up (default 1.1x); and for ads a cold open plus a CTA end card made from a clean, uncaptioned frame.

## 6. Check: mandatory, never skip
**First, run the full self-check in `references/self-qa.md`** (re-transcribe the finished video and read it like a viewer, cut only on real silence, numbers appear only when spoken, music under the voice). The person must never be the one who finds a mistake.
`$PY $TBM check all --project <dir>` reports, for every output: flash/glitch frames (must be `[]`), host words found in a fresh transcript (must be `[]`), eye-line stability, and faces near the caption area (often false alarms from hands or the mic, so verify by eye). Then **look at every contact sheet** in `out/checks/` as a viewer would:
- Is the main speaker on screen and well framed, with no shoes, empty couch or lamp shots?
- Is any text covering a face? Is the text readable? Are any words wrong (names, brands, numbers)? Add those to `"fixes"` in config.json.
- Do the first 2 seconds hook? Does the clip end on the payoff?
- Does the ad end card show clean text with no leftover caption underneath?
Fix, rebuild, re-check. Only report "done" when every file passes. Tell the user what you checked and what you found.

## 7. Deliver
Copy `out/reels` and `out/ads` to the user's folder. Write `TITLES_AND_DESCRIPTIONS.md`: for each clip, a title under 60 characters (curiosity or contrarian, plus a keyword the audience searches) and a 2 to 3 line description from what is actually said in the clip, ending with the CTA line and hashtags; plus Meta primary text for each ad. Never invent claims or numbers; use only what the speaker said.

## Hard rules (learned from real feedback, never break these)
1. No white title boxes or hook-text boxes over the video unless the user asks. Captions only.
2. Nothing may ever cover the face.
3. Keep the main person on screen. No stacked split-screens with the host. Moments that show only the host are cut or covered with B-roll.
4. Remove the host's reactions and questions, then verify by re-transcribing the finished file.
5. Wide shots become head-and-shoulders crops, never full body.
6. Eyes stay on one horizontal line through cuts and zooms (from a professional editor's feedback).
7. Every clip starts on a strong complete sentence and ends on the payoff.
8. Fix transcription errors in captions: names, brands (ChatGPT), "reason" vs "region", currency.
9. Check before saying done: run `check`, look at the sheets, and report honestly what was found and fixed.
10. Ask before downloading anything from the internet.
11. Never deliver before `references/self-qa.md` passes. Re-transcribe the finished video, fix every broken join, repeat, chat-box line, dead air and placeholder number yourself, then report what you checked.

12. **Legs: use judgment.** For a seated speaker, crop head-and-chest so a moving lap or legs never distract. For a standing or walking speaker, full body is fine. Ask if unsure.
13. **Ads: ask, don't assume.** Ask what goes at the top: an audience call-out badge (e.g. "FOR COACHES"; Meta's Andromeda update rewards ads that say who they are for), a simple headline or title, or nothing. Also ask the hook text, length (30-45 s works well), and music (none by default). Then loudness -14 LUFS, 9:16.
14. **Storyboard first.** Before rendering many videos, show 1 preview or a few still frames and get the student's OK. It saves hours of rework.
15. **Look for the other person in every contact sheet.** Split-screen shots can slip a host-only frame into the crop; cut it.
16. **Show finished videos early** while the rest build, and give an honest time estimate.

17. **Get the clip list approved before building.** Show the planned clips (hook + one line each), let the student pick, build only those. It saves hours.
18. **Show proof on screen** when the speaker mentions a real result: ask for the screenshot (post, comments, sales) and show it as a card zoomed on the numbers.

22. **Headline = curiosity hook, bigger font.** The top headline must make people need to watch to the end: an open loop, a surprising number, a confession or a contrarian claim, never a plain topic label ("Talk values" is a label; "I never knew my niche. Here's what I posted instead" is a hook). 5 to 9 words, the speaker's own words where possible, never a claim they didn't make. Font 104, max 2 lines. Always show 2-3 headline options per reel in the storyboard and get approval before rendering.

23. **Proven reel style (from instagram.com/p/Dc7_blITEAh, offer it as an option).** Headline = a quoted viewer objection in curly quotes, UPPERCASE, Impact 96 (config `"headline": {"size": 96}`), line 1 white, line 2 in the creator's brand colour (`"“WHY WOULD ANYONE|*LEAVE A SAFE JOB?”*"`; `|` places the line break). Captions = `"style": "quiet"` (1-3 small white words, natural case, one line). Soft shading under the text. Animated proof scenes on the key lines.

24. **Proofread subtitles like an expert in the creator's business** before delivery. Read every caption line and ask the creator for their key words (programme names, tools, places) at the start. Common fixes: Claude Code (not Cloud Code), ChatGPT, paid ads (not feed/PR ads), 1 crore / 2 crore, lakh, LinkedIn, WhatsApp, AI in capitals, "serve my clients" (Whisper often hears "solve"). Never lowercase captions (AI, LinkedIn and brand names keep their capitals).

25. **Storyboard = real frames.** Before building a batch, render ONE complete sample and show a 6-frame storyboard sheet cut from it (hook headline, caption look, each animated scene, ending), labelled with timestamps. The creator approves the sheet + sample, then the rest is built. For full-frame footage keep `"headline": {"shade": true}` (the default) so the text sits on a soft shade, never a gradient over burned-in text.

26. **Guest only, ever.** When the creator is a guest on someone's podcast and asks for only themselves on screen, NO frame may show the host or the podcast's stock inserts, not even a 1 s reaction shot. The engine check misses these: run `scripts/hostscan.py <reels>` and cover every hit (a card with the creator's words over their own dimmed frame, or cut it). hostscan tells people apart by shirt colour: first calibrate it on one known frame of each person (it ships tuned for a lime shirt vs a grey jacket). Hits can also hide UNDER a see-through animated scene, so cover those too. Deliver only when every reel scans [].

27. **The creator's face stays on screen the whole reel** (Nate Herk style). Animated scenes are NEVER a black full-screen: they float over the video with only the video area dimmed (a soft dark box around 45%), so the headline and captions stay bright. Host cut-aways are covered with the creator's own clean frame (dimmed) plus their words. Card text is never the same colour as its card (brand-colour text on a brand-colour card disappears).

28. **Sound is optional, default none.** Voice only unless the creator picks Light or Full (question 9). Then run `scripts/sfx.py <reel.mp4> light|full --at "0.1:pop,24.5:hit"` with times from the transcript (headline start, CTA start, cuts for full), never on the hook's first words or a punchline, at most one sound every 3 s. The sounds are made by code, so they are free for ads with no credit; extra sounds from openverse.org only if marked CC0, saved as `sfx/<name>.wav`. Tell them which seconds have a sound, and if it feels noisy go one step down. Loudness stays -14 LUFS.

29. **Missed speech.** Whisper sometimes skips a whole stretch (more often in Hinglish). Compare the transcript timings with the audio; if a gap has speech, re-transcribe just that time range on its own. Words added back this way may have rough timing, so check them on the contact sheet.

30. **Save the student's Claude usage.** One new session per video (long chats cost more every message), approve the storyboard before rendering, ask them to send all changes in one message, and reuse their `style-guide.md` instead of studying references again.

31. **Any language, checked words.** For Hindi, Tamil, Bengali, Odia and other languages, follow `references/cloud-and-languages.md`: read with two engines, let the student confirm the words, never guess a missing line, and use their script for weak languages. Show the three caption looks on their own video so they pick from a picture. Before delivery, run the phone-size check and re-transcribe the finished reel against the captions.

32. **Cloud or Windows.** If the student is in Claude Code on the web (or on Windows), use the upload page and watch-and-save page from the `tbm-short-form-video` skill for big videos and full-quality delivery.

## Style references
**Learn a student's style once.** When they share 3-5 reels they like (links, or files dropped in `Reference/`): download each with yt-dlp into `Reference/` (ask first, rule 10), study frames, cuts and transcript (layout, fonts, colours, captions, zooms, pacing, motion graphics, sound), and write `style-guide.md` in their project with exact colour codes, sizes and timings. Inspire, don't copy: build their own look from their own footage, never reuse another creator's graphics or words. If Instagram says "This content isn't available to everyone", the reel needs a login: either the student lets yt-dlp use their Chrome login (`--cookies-from-browser chrome`; macOS may ask to allow "Chrome Safe Storage", only for their own downloads), or they save the video themselves and drop it in `Reference/`. Then let them correct the guide ("use #1E66F5, bigger captions") and follow it on every video.

See `references/style-guide.md` for what top creators do (podcast clips in the style of Raj Shamani and Ranveer Allahbadia; solo talking-head in the style of Matt Gray). Update that file when the user shares reference reels.

## Feedback loop
This skill improves with every project. When the user gives feedback ("text is over my face", "too much of the host", "eyes should stay on one line"):
1. Fix the current videos.
2. Add the lesson to **Hard rules** above (or to config defaults or the scripts, if it can be automated), and log it in `references/feedback-log.md` with the date.
3. If it can be checked automatically, add it to `check`.
