from pathlib import Path

from sourcemode import video as V


def test_a_template_run_gives_every_leg_its_own_line_and_its_own_camera_clause():
    spec = V.VideoSpec(character="nadia", motion="", seconds=25, legs=["a", "b", "c", "d", "e"],
                       leg_suffix="his point of view", size=[1280, 720], template="velvet_lounge",
                       source={"kind": "keeper", "path": __file__})
    assert V.validate(spec, leg_cap_s=6.0) == []
    assert V.legs_for_template(25, 5) == [5.0] * 5
    # four legs cannot cover 25 s at a 6 s cap
    short = V.VideoSpec(**{**spec.__dict__, "legs": ["a", "b", "c", "d"]})
    assert any("cannot cover" in p for p in V.validate(short, leg_cap_s=6.0))


def test_the_script_becomes_timed_beats():
    beats = V.script_beats("[1-6s] Hi. You look tense.\n[7-9s] Just relax for me.\nYes.\n")
    assert beats == [(1.0, "Hi. You look tense."), (7.0, "Just relax for me."), (10.0, "Yes.")]


def test_each_line_is_laid_under_the_clip_at_its_time_and_the_picture_is_copied():
    args = V.voice_mux_args(Path("take.mp4"), [(1.0, Path("a.wav")), (7.5, Path("b.wav"))],
                            Path("out.mp4"), ffmpeg="ffmpeg", seconds=24.5)
    fc = args[args.index("-filter_complex") + 1]
    assert "adelay=1000|1000" in fc and "adelay=7500|7500" in fc and "amix=inputs=2" in fc and "apad=whole_dur=24.500" in fc and "atrim=0:24.500" in fc
    assert args[args.index("-c:v") + 1] == "copy" and "-shortest" not in args


def test_a_music_bed_loops_under_the_lines_and_fades_out_at_the_end():
    args = V.voice_mux_args(Path("take.mp4"), [(1.0, Path("a.wav"))], Path("out.mp4"), ffmpeg="ffmpeg",
                            seconds=240.0, music=Path("bed.mp3"), music_db=-14)
    i = args.index(str(Path("bed.mp3")))
    assert args[i - 3:i - 1] == ["-stream_loop", "-1"]
    fc = args[args.index("-filter_complex") + 1]
    assert "[2:a]atrim=0:240.000" in fc and "volume=-14dB" in fc and "afade=t=out:st=235.000:d=5" in fc
    assert "[a1][mus]amix=inputs=2" in fc
    # music alone, no lines
    fc = V.voice_mux_args(Path("t.mp4"), [], Path("o.mp4"), ffmpeg="ffmpeg", seconds=30.0, music=Path("m.mp3"))
    assert "[mus]amix=inputs=1" in fc[fc.index("-filter_complex") + 1]
