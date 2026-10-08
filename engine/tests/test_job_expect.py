"""A queued job carries what it will produce; the page reads that, not the command.

Nine command-line parsers on the page, and every new job shape produced a wrong
card. The parse now happens once, at `gpu add`, and is stored on the job as
`expect` - the page counts where the record says to count.
"""

from pathlib import Path

from sourcemode.gpu import queue as q
from sourcemode.monitor.queue_page import expect_for, job_done, job_expect, render_target


def test_the_record_wins_over_a_command_the_page_cannot_read():
    job = {"cmd": ["something", "nobody", "has", "seen"],
           "expect": {"total": 40, "what": "2 epochs x 20 scenes"}}
    assert job_expect(job) == (40, "2 epochs x 20 scenes")


def test_a_job_queued_before_expect_existed_still_falls_back_to_the_parse():
    cmd = ["python", "scripts/eval/dense_epoch_eval.py", "mei", "mei_v2", "24", "16", "24",
           "mei", "outputs/lora-datasets/mei_v2/lora", "20", "--epochs", "22,23"]
    assert job_expect({"cmd": cmd}) == (40, "2 epochs x 20 scenes")
    assert job_expect({"cmd": cmd, "expect": None}) == (40, "2 epochs x 20 scenes")


def test_done_is_counted_where_the_record_points(tmp_path):
    d = tmp_path / "dense_x_asset_tag"
    (d / "ep22").mkdir(parents=True)
    (d / "ep22" / "scene_00.png").write_bytes(b"")
    (d / "ep22" / "scene_01.png").write_bytes(b"")
    (d / "ep22" / "_web").mkdir()
    (d / "ep22" / "_web" / "scene_00.png").write_bytes(b"")      # a thumbnail, not a render
    job = {"cmd": ["x"], "expect": {"total": 40, "what": "", "dir": str(d), "glob": "scene_*.png"}}
    assert job_done({}, job) == 2
    job["expect"]["dir"] = str(tmp_path / "not-yet")
    assert job_done({}, job) == 0


def test_a_tagged_sweep_is_counted_in_its_own_folder(tmp_path):
    cfg = {"paths": {"outputs": str(tmp_path)}}
    cmd = ["python", "scripts/eval/dense_epoch_eval.py", "mei", "mei_v2", "24", "16", "24",
           "mei", "outputs/lora-datasets/mei_v2/lora", "20", "--epochs", "22,23", "--tag", "nodesc"]
    assert render_target(cfg, cmd) == (tmp_path / "dense_mei_v2_asset_nodesc", "scene_*.png")
    e = expect_for(cfg, cmd)
    assert e == {"total": 40, "what": "2 epochs x 20 scenes",
                 "dir": str(tmp_path / "dense_mei_v2_asset_nodesc"), "glob": "scene_*.png"}


def test_an_ab_counts_its_tag_folder_and_an_unknown_command_has_no_record(tmp_path):
    cfg = {"paths": {"outputs": str(tmp_path)}}
    cmd = ["python", "scripts/eval/prompt_ab.py", "cat", "cat_v2", "23", "C:/l", "cat",
           "--tag", "desc", "--find", "@clause", "--arms", "A==|B=a woman", "--scenes", "0,1,2"]
    assert expect_for(cfg, cmd) == {"total": 6, "what": "2 arms x 3 scenes",
                                    "dir": str(tmp_path / "ab_cat_desc"), "glob": "scene_*.png"}
    assert expect_for(cfg, ["powershell.exe", "-File", "character_chain.ps1"]) is None


def test_expect_is_stored_on_the_job_and_survives_a_round_trip(tmp_path):
    path = q.queue_path(tmp_path)
    doc = q.empty()
    q.add(doc, kind="eval", label="x", cmd=["x"], cwd=".", expect={"total": 3, "what": "3 things"})
    q.add(doc, kind="eval", label="y", cmd=["y"], cwd=".")
    q.save(path, doc)
    jobs = q.load(path)["jobs"]
    assert jobs[0]["expect"] == {"total": 3, "what": "3 things"}
    assert jobs[1]["expect"] is None
    assert Path(path).is_file()
