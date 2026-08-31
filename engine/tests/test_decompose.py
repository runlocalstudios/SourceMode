import json
from pathlib import Path

from sourcemode.prompts.decompose import Qwen3Decomposer, RuleBasedDecomposer

EVALS = Path(__file__).resolve().parent.parent / "evals" / "decomposer_cases.json"


def test_rule_based_against_checked_in_evals():
    cases = json.loads(EVALS.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 6
    decomposer = RuleBasedDecomposer()
    for case in cases:
        shots = decomposer.decompose(case["brief"])
        assert len(shots) == case["expected_shot_count"], case["name"]
        assert [s.camera_move for s in shots] == case["expected_camera_moves"], case["name"]
        if "expected_speeds" in case:
            assert [s.speed for s in shots] == case["expected_speeds"], case["name"]
        if "expected_emotions" in case:
            assert [s.emotion for s in shots] == case["expected_emotions"], case["name"]
        for s in shots:
            assert s.duration_s <= 8.0


MARKET_BRIEF = (
    "Gwen walks slowly through a rainy neon market at night, worried, "
    "the camera tracks her from behind then swings around to her face"
)


def test_camera_clause_strip_leaves_no_dangling_words():
    shots = RuleBasedDecomposer().decompose(MARKET_BRIEF)
    for s in shots:
        assert "camera" not in s.motion.lower()
        assert not s.motion.rstrip().endswith((" the", " a", " an", " and", " then", " at", " to"))
    assert shots[0].motion == "Gwen walks through a rainy neon market at night"


def test_two_camera_phases_become_two_shots():
    shots = RuleBasedDecomposer().decompose(MARKET_BRIEF)
    assert [s.camera_move for s in shots] == ["tracking", "orbital arc"]
    assert [s.idx for s in shots] == [0, 1]
    assert shots[0].motion == shots[1].motion  # same action, camera phase differs
    assert all(s.duration_s <= 6.0 for s in shots)  # split beats get shorter shots


def test_trailing_preposition_cleaned_when_camera_is_object():
    shots = RuleBasedDecomposer().decompose(
        "Gwen looks up from her phone and smiles at the camera"
    )
    assert shots[0].motion == "Gwen looks up from her phone and smiles"


def test_rule_based_is_deterministic():
    brief = "Gwen walks slowly through a rainy neon market, worried, camera tracks from behind"
    a = RuleBasedDecomposer().decompose(brief)
    b = RuleBasedDecomposer().decompose(brief)
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]


def test_qwen3_decomposer_with_mocked_transport():
    calls = {}

    def transport(url, payload):
        calls["url"] = url
        calls["payload"] = payload
        content = json.dumps([
            {
                "idx": 0, "shot_size": "WS", "lens": 24, "camera_move": "tracking",
                "motion": "walks through the market", "speed": "slowly", "emotion": "worried",
                "environment": "rainy neon market", "lighting": "neon glow",
                "grade": "teal-orange", "duration_s": 12,
            }
        ])
        return {"choices": [{"message": {"content": f"```json\n{content}\n```"}}]}

    decomposer = Qwen3Decomposer("http://localhost:11434/v1", model="qwen3", transport=transport)
    shots = decomposer.decompose("Gwen walks through a rainy market")
    assert calls["url"] == "http://localhost:11434/v1/chat/completions"
    assert calls["payload"]["messages"][0]["role"] == "system"
    assert "cinematographer" in calls["payload"]["messages"][0]["content"]
    assert len(shots) == 1
    assert shots[0].camera_move == "tracking"
    assert shots[0].duration_s == 8.0  # capped from 12


def test_qwen3_decomposer_invalid_camera_falls_back_to_static():
    def transport(url, payload):
        content = json.dumps([
            {"idx": 0, "shot_size": "MS", "lens": 35, "camera_move": "barrel roll",
             "motion": "stands", "speed": "steadily", "emotion": "calm",
             "environment": "studio", "lighting": "soft", "grade": "neutral", "duration_s": 4}
        ])
        return {"choices": [{"message": {"content": content}}]}

    shots = Qwen3Decomposer("http://x", transport=transport).decompose("brief")
    assert shots[0].camera_move == "static"
