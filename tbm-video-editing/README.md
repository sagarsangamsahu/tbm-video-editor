# TBM Video Editing skill: student guide

Turn any long video (podcast, interview, webinar) or your raw phone recording into ready-to-post Reels / Shorts, paid ads and titles, by chatting with Claude.

## One-time setup (10-20 minutes, Mac or Windows)
1. Install the **Claude** desktop app and open **Claude Code**. Windows only: also install **Git for Windows**.
2. Put this zip in a folder (e.g. `My Reels`) and add that folder in Claude Code.
3. Say: **"Set up the TBM video editing skill."** Claude unzips the skill into `~/.claude/skills/tbm-video-editing/` and runs `scripts/setup.py`. That installs ffmpeg, Whisper and the rest (Homebrew on Mac, winget on Windows) and ends with **READY**.
   - Mac without Homebrew: Claude will ask you to paste one line from https://brew.sh into the Terminal app and type your laptop password.
   - The first setup downloads about 1-2 GB, so stay plugged in and online.

## Your folders (make once)
One main folder (e.g. `My Reels`) with three folders inside:
- `Raw Footage/`: your original recordings. Claude reads them and never changes them.
- `Reference/`: reels whose editing you like, so Claude can learn the style.
- `Export/`: finished videos land here.
Claude adds its own working folders later. Ignore them, but don't delete them if you may want changes.

## Teach Claude your style (once)
Say: "Learn the editing style from these reels: <link 1> <link 2> <link 3>. Download them into Reference, then write my style-guide.md. Inspire, don't copy." Read the guide and correct it ("use my colour #1E66F5, bigger captions"). Every next video follows it.
If Instagram says "This content isn't available to everyone": tell Claude it may use your Chrome login, or save the reel yourself and drag it into `Reference/`.

## Every time
1. Open Claude Code in your main folder. Start a **new session for each video**.
2. Say something like:
   - "Make 10 reels from this podcast: <Google Drive link>"
   - "Edit my raw video into a reel: <file or link>"
   - "Make 3 ads from this, CTA: register for my free webinar"
3. Answer Claude's few questions: who's the main person, your brand colours, your CTA.
4. Wait while it works (roughly 2 to 5 minutes per clip). Claude checks every video before handing it over.
5. You get: `reels/`, `ads/` and `TITLES_AND_DESCRIPTIONS.md`.

## Tips for the best results
- Share the Drive link with "Anyone with the link can view".
- Raw recordings: phone on a tripod (Claude can add zooms, not fix shake), a clip-on mic (clean audio = correct captions), leave space above your head for zooms, face the camera, light from the front, and pause between takes. Claude removes the bad takes.
- Tell Claude your spoken language (English / Hindi / Hinglish), whether captions should be Roman or Devanagari, and your brand and tool names (Whisper hears "Claude" as "cloud").
- Approve the storyboard before the full render, and send all your changes in one message. Both save your Claude limit.
- Watch the whole video with sound before posting.

## If something goes wrong
| You see | Fix |
|---|---|
| Typing your password shows nothing | Normal. Keep typing, then press Return |
| `Sorry, try again` | Wrong password. Type slowly, check Caps Lock |
| `command not found` right after typing your password | You typed it at the normal prompt. Run `rm -f ~/.zsh_history`, then do the step again |
| A "Command Line Tools" pop-up during Homebrew | Click Install, wait for it to finish, then run the Homebrew line again |
| `command not found: brew` | Run `echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile`, then open a new Terminal window |
| Captions skip part of what you said | Ask Claude to transcribe that time range again |
| Claude can't change a setting (safety check) | Claude gives you the command; run it yourself |
| Anything else | Paste the error or a screenshot into Claude: "Fix this step by step" |
- Tell Claude what you don't like ("text is covering my face", "too slow"). It fixes the videos **and remembers** the lesson in the skill.
