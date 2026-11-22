# Self-check before delivery (mandatory, every video, every time)

The person should NEVER be the one who finds a mistake. You find it first. Do not say "done" until every step below passes.
Learned the hard way on Sagar's Mission 02 YouTube edit (Oct 2026): 17 mistakes in the first cut, a "0 paid" counter, music too loud.

## 1. Listen to the finished cut as words (re-transcribe it)
Transcribe the FINISHED video again (not the source). Read the whole transcript top to bottom like a viewer and fix:
- **Broken joins**: two different sentences glued together ("start with the offer, coach number A, okay, or coach number B").
- **Chopped sentences**: a sentence that stops mid-way ("that is going to give..."), or a stray first word of a removed part ("Plus", "People may call").
- **Repeats**: the same question or line said twice.
- **Live-call talk**: "type in the chat box", "is it making sense?", roll calls, internet trouble, names of people in the room.
- **Dead air**: any silence over 1 second, especially at a join or at the end.
- **Out-of-context lines**: something that worked live but sounds wrong alone (bragging, an inside joke).
- **Garbled bits**: half-sentences, "it's not the price, it's the price".
- **The ending**: the last words must be a complete, clean sentence. No trailing "So." or "Okay."

## 2. Cut on real silence, not on transcript times
Whisper word times drift up to about 1 second on long audio. Before you cut, check the real silence with
`ffmpeg -ss A -to B -i video -af silencedetect=n=-34dB:d=0.1 -f null -` or re-transcribe just that 3 to 5 seconds with word timestamps.
Snap every cut to a real silence. Then re-transcribe and confirm the join reads cleanly.

## 3. Graphics and numbers
- A number or word appears ONLY when it is spoken. Never show a placeholder ("0 paid", "₹0") or count up from 0 while the speaker is still talking about something else.
- Every graphic element starts inside its own card's time. Cards never overlap.
- No text over a face. Nothing cut off at the edge of the screen. Long numbers fit on one line.
- Names on screen come from the video's own name label or the person. Never guess a name from the transcript (transcripts misspell names). If unsure, use a role ("TBM member").
- Look at a frame for EVERY card (snapshot at the card's middle) before the final render.

## 4. Sound
- Final loudness about -14 LUFS (check with `ffmpeg -i out.mp4 -af ebur128 -f null -`).
- Music sits clearly UNDER the voice. If in doubt, make it quieter. Sagar's feedback: the first music bed was too loud.
- Sound effects only on things that appear on screen; none on every cut.

## 5. Report honestly
Tell the person what you checked, what you found and what you fixed. If something is still not perfect, say it plainly.
