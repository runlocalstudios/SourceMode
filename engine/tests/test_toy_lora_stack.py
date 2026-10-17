"""The toy shoot renders with the torso LoRA under hers (Jeremy, 2026-10-17).

The T2I template has one spare LoraLoader after hers. The shoot names the lock
id, the run script resolves it, and the graph carries it at 0.6 - never more,
because a non-identity LoRA above 0.6 fights her face.
"""

from __future__ import annotations

import json

import pytest

from sourcemode.assets import lora as L
from sourcemode.assets.render import t2i_workflow
from sourcemode.render.workflow import LoraCompositionError

CFG = {
    "paths": {"workflows": "../workflows", "outputs": "outputs"},
    "models": {"qwen_image": "qwen.safetensors", "qwen_text_encoder": "te.safetensors",
               "qwen_vae": "vae.safetensors"},
    "render": {"qwen_shift": 3.1, "medium": {"qwen_t2i_steps": 20, "qwen_t2i_cfg": 4.0}},
}


def _loras(graph: dict) -> list[tuple[str, float]]:
    return [(n["inputs"]["lora_name"], float(n["inputs"]["strength_model"]))
            for n in graph.values() if n["class_type"] == "LoraLoaderModelOnly"]


def test_her_lora_alone_leaves_one_loader_in_the_graph():
    g = t2i_workflow(CFG, "p", 1, "x", lora_path="sourcemode/amanda.safetensors", negative="n")
    assert _loras(g) == [("sourcemode/amanda.safetensors", 1.0)]


def test_the_torso_lora_sits_under_hers_at_its_own_strength():
    g = t2i_workflow(CFG, "p", 1, "x", lora_path="sourcemode/amanda.safetensors", negative="n",
                     extra_loras=(("sourcemode/torso.safetensors", 0.6),))
    assert _loras(g) == [("sourcemode/amanda.safetensors", 1.0),
                         ("sourcemode/torso.safetensors", 0.6)]
    # chained: the torso loader takes the model from hers
    ids = {n["inputs"]["lora_name"]: k for k, n in g.items() if n["class_type"] == "LoraLoaderModelOnly"}
    assert g[ids["sourcemode/torso.safetensors"]]["inputs"]["model"][0] == ids["sourcemode/amanda.safetensors"]


def test_an_object_lora_above_point_six_or_a_second_one_is_refused():
    with pytest.raises(LoraCompositionError):
        t2i_workflow(CFG, "p", 1, "x", lora_path="a.safetensors", negative="n",
                     extra_loras=(("t.safetensors", 0.8),))
    with pytest.raises(ValueError):
        t2i_workflow(CFG, "p", 1, "x", lora_path="a.safetensors", negative="n",
                     extra_loras=(("t.safetensors", 0.5), ("u.safetensors", 0.5)))


def test_an_object_set_is_not_a_character_the_shoots_tab_offers(tmp_path):
    # the torso is locked so the toy shoot can stack it; its preview trigger is
    # "torsotoy", not "torso", which is the GPU page's own object rule
    (tmp_path / "previews").mkdir()
    (tmp_path / "previews" / "torso_v1.json").write_text(json.dumps({"trigger": "torsotoy"}), encoding="utf-8")
    (tmp_path / "previews" / "winnie_v2.json").write_text(json.dumps({"trigger": "winnie"}), encoding="utf-8")
    cfg = {"train": {"previews": str(tmp_path)}}
    assert L.is_object_set(cfg, "torso_v1", "torso")
    assert not L.is_object_set(cfg, "winnie_v2", "winnie")
    assert not L.is_object_set(cfg, "nobody_v2", "nobody")   # no preview: not an object
