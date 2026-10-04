"""Script, plates and pacing for Jojo's late-night selfie videos.

Jeremy, 2026-09-28: six 6-second clips in sexier pyjamas with a cute flirty
late-night script, then two 12-second ones.

His note on the earlier stitched videos, and the whole reason the pacing block
below exists: "the motion in the 2nd or 3rd legs was much more rapid than the
first leg - for multi-leg vids the speed of speech and motion should be [stated]
in the prompt for consistency across legs."

Two things are done about that, because one alone would not be enough:

  1. ONE audio clip per video, encoded ONCE, feeding both legs. Under S2V the
     mouth and the head motion are driven by the audio, so a single continuous
     timeline cannot speed up at a seam the way two separately generated clips
     can. This is the structural fix.
  2. PACING is a literal, identical clause in every leg's prompt, and the TTS
     cfg_weight is held at one value across the whole set. Chatterbox's own
     docs note cfg_weight ~0.3 slows delivery; 0.4 is a slightly relaxed,
     unhurried read, which is what a late-night selfie should sound like.

Identity traits are never named - the LoRA supplies her face and hair. Framing is
head-and-chest so the face keeps its pixel budget; the first selfie test failed
because it was rendered at the video bucket instead of the training bucket.
"""

# --- pacing, stated identically on every leg of every video --------------------
PACING = ("she speaks slowly and softly at an unhurried, even pace, her head and "
          "shoulders moving gently and only a little, no sudden movement")

# --- the plate: what she looks like, held constant across all six --------------
# 1024x1536 (the TRAINING bucket), then resized and centre-cropped to 720x1280
# for Wan. Rendering straight at 720x1280 cost 349-468px faces against a 623px
# median in her working sweep, and not one of twelve looked like her.
PLATE_W, PLATE_H = 1024, 1536
VIDEO_W, VIDEO_H = 720, 1280

PYJAMAS = [
    "a short silky black cami pyjama set with thin straps",
    "a cropped white ribbed pyjama top with tiny shorts",
    "an oversized soft pink sleep shirt slipping off one shoulder",
    "a lace-trimmed satin champagne cami and shorts set",
    "a thin grey cotton sleep tank with matching shorts",
    "a deep red silk pyjama shirt with the top buttons undone",
]

SETTINGS = [
    "sitting on the edge of her bed with a warm bedside lamp behind her",
    "lying propped on one elbow against her pillows, lamplight low",
    "sitting cross-legged on her bed, the room dim behind her",
    "leaning back against her headboard under a soft lamp",
    "sitting on her bed with fairy lights blurred on the wall behind her",
    "half-sitting against her pillows, one lamp on, the rest of the room dark",
]

# --- the script: six lines, each about six seconds spoken ---------------------
# Flirty and warm rather than explicit, so a moderation refusal cannot stall the
# batch, and short enough that 97 frames at 16 fps (6.06 s) covers the line.
LINES_6S = [
    "Hey you. I know it's really late, I'm sorry. I just got into bed and I "
    "couldn't stop thinking about you, and I figured you were probably still up too.",

    "I should have been asleep hours ago. But then I started thinking about you "
    "again, and now I'm just lying here wide awake, talking to my phone like this.",

    "Okay, be honest with me. Do you like these? I picked them out this afternoon, "
    "and the entire time I was standing there I was wondering what you'd think.",

    "It is so quiet in here tonight. The whole house is asleep and it's just me, "
    "and I keep wishing you were over here instead of all the way over there.",

    "I really can't sleep. Tell me something, anything at all, I don't even mind "
    "what it is. I just want to hear your voice for a while before I drift off.",

    "Alright, I am going to send you this one and then I promise I'll behave myself "
    "and go to sleep. Probably. I'm not making any actual promises here, though.",
]

# --- the two longer ones: about twelve seconds each ---------------------------
LINES_12S = [
    "Hey. It's really late, I know, and I know I keep doing this to you. I just got "
    "into bed and the whole house has gone quiet, and I was lying here in the dark "
    "and I realised you are honestly the only thing I have been thinking about all "
    "evening. Is that bad? I've decided it isn't bad. I've decided it is completely fine.",

    "Okay so I have a bit of a confession to make. I picked these out earlier today, "
    "and the entire time I was standing there looking at them, I was wondering what "
    "your face would do if you saw me wearing them. And now it is somehow past "
    "midnight, and I am still lying here wide awake, still wondering about it.",
]

# --- frame budgets -------------------------------------------------------------
# WanSoundImageToVideo length: min 1, step 4, default 77. 4n+1 keeps the VAE happy.
FPS = 16
MAX_LEG = 121           # frames per leg; longer has exhausted RAM here before


def frames_for(seconds):
    """Video length must match the SPEECH, not a guess. The first pass asked for
    6-second clips against 3.3 seconds of audio, which would have been half a clip
    of a woman silently staring. Snap up to 4n+1, which is what the VAE wants."""
    n = int(seconds * FPS) + 1
    return max(5, n + ((4 - (n - 1) % 4) % 4))


def legs_for(seconds):
    """Split a long line into equal legs of <=MAX_LEG. Equal, because a short tail
    leg is exactly where a change of pace would show against the others."""
    total = frames_for(seconds)
    if total <= MAX_LEG:
        return [total]
    n = -(-total // MAX_LEG)
    return [frames_for(seconds / n)] * n


def video_prompt(pyjamas: str, setting: str) -> str:
    """One prompt shape, reused for every leg so nothing changes at a seam."""
    return (f"a young woman {setting}, wearing {pyjamas}, holding her phone at "
            f"arm's length and talking to the camera, head and chest in frame, "
            f"warm low lamplight, {PACING}")


def plate_prompt(trigger: str, pyjamas: str, setting: str) -> str:
    return (f"{trigger}, a woman, taking a selfie photo, her arm outstretched and "
            f"visible in the frame, wearing {pyjamas}, {setting}, "
            f"a head-and-chest portrait, warm low lamplight, a soft flirty smile")


if __name__ == "__main__":
    print(f"{len(LINES_6S)} short clips, {len(LINES_12S)} long clips")
    for sec in (3.3, 6.0, 12.0, 14.0):
        print(f"  {sec:>5.1f}s speech -> {frames_for(sec):>4} frames, legs {legs_for(sec)}")
    assert len(PYJAMAS) == len(SETTINGS) == len(LINES_6S) == 6
    assert all((f - 1) % 4 == 0 for f in (frames_for(6.0), frames_for(12.0)))
    print("  words, short:", [len(t.split()) for t in LINES_6S])
    print("  words, long :", [len(t.split()) for t in LINES_12S])
    print("sample plate: " + plate_prompt("jojo", PYJAMAS[0], SETTINGS[0])[:140])
