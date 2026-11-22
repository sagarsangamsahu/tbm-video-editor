# Learnings from the TBM Reel Editor 0.6 (7-day challenge cloud skill)

Added Nov 17 2026. The working tools live inside the `tbm-short-form-video` skill (one SKILL.md that writes its own `tools/` when you run its extract step). Reuse those tools instead of rebuilding them.

## 1. Any language, with the right speech engine
| Spoken language | Engine | Notes |
|---|---|---|
| English | `parakeet` | Exact word times, most reliable |
| Hindi, Bengali, Tamil, Telugu, Gujarati, Odia, Marathi, Urdu, Nepali | `--engine all` (Dolphin + Whisper) | Dolphin gives real word times but merges or misses words; Whisper is fuller text with spread-out times. Read both, mark where they differ |
| Kannada, Malayalam, Punjabi, Assamese and weak languages | The speaker's own script + `align_script.py` | Engines read these poorly. Time their script against the speech |
| Hinglish | `--engine all --lang hi` | Main language as `--lang`; fix script and spellings |
- **The speaker always confirms the words** for every non-English video: show the combined text with the time of every doubtful line, then write the confirmed lines to `pages.json`.
- **Never fill a gap with guessed words.** A stretch with no confirmed text gets no caption, and you say so.
- Captions can be in the spoken language, a translation they ask for, or the same words in Roman letters. The tool downloads the matching Noto font (Devanagari, Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Odia, Arabic, Thai); check for empty boxes.

## 2. Show caption looks on their own video
`looks.py` renders the same 4 seconds in three looks side by side: **karaoke** (spoken word lights up), **plain** (short line), **word** (one big word at a time). Let them pick from the picture instead of describing styles.

## 3. Checks before anyone sees it
- **Phone-size check:** a 360 px wide frame; every word must be easy to read at that size.
- **Re-listen check:** transcribe the finished reel again and compare with the caption lines; a word cut in half, a missing word or a mismatched line is fixed before delivery.
- **Lost-sound check:** any sound that was cut with no words in it is listed by time (often a breath, sometimes a missed word).
- Say plainly that you cannot hear, and ask for one watch with sound on.

## 4. Working in Claude Code on the web (cloud)
- **Upload page:** chat attachments stop at about 30 MB, so big phone videos come through a private Artifact upload page in 20 MB pieces, rejoined and checked by SHA-256.
- **Watch-and-save page:** the finished reel goes back at full quality in pieces with a "Save to my device" button.
- Speech models download from GitHub (Hugging Face is often blocked in the cloud). If a host is blocked: environment menu → Edit → Network access → add `github.com`.
- Remind them to save the reel before closing: a cloud session can restart and wipe files.
- Windows users: send them to claude.ai/code in the browser instead of a half local setup.

## 5. Working habits
- **No blank answers:** if a question is skipped or half answered, ask again for the missing part; "you decide" means decide and say what you chose.
- **Open with the point:** the first strong sentence lands in the first 3 seconds, with the headline on screen from the first frame.
- **Notes for restarts:** keep `work/NOTES.md` with each choice and the next step; after a restart, read it first.
- **Ad safe zone:** `"safe": "ad"` lifts captions clear of the ad buttons when a reel may be boosted.
- **Variations:** from one short clip, build hook versions, a 15-30 s teaser, other formats and 4:5 / 1:1 copies with `variants.py`.
