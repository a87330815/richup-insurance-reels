import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from contentagent import accounts, compliance, draft, presets, render

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "agents/content/examples/richup/script.json"


def sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class AccountsTest(unittest.TestCase):
    def test_every_account_loads(self):
        ids = accounts.list_ids()
        self.assertIn("richup", ids)
        for a in ids:
            cfg = accounts.load(a)
            presets.collect(cfg)  # 없는 프리셋이면 실패
            self.assertTrue(cfg["delivery"].get("drive_folder_id"), a)

    def test_template_has_all_required_keys(self):
        t = json.loads((accounts.ACCOUNTS / "_template.json").read_text(encoding="utf-8"))
        for k in accounts.REQUIRED:
            self.assertIn(k, t)

    def test_plan_weekday_and_weekend(self):
        cfg = accounts.load("richup")
        wed = accounts.plan(cfg, datetime(2026, 11, 25, 9, tzinfo=accounts.KST))
        self.assertEqual(wed["series"]["name"], "보험금 청구 꿀팁")
        self.assertIsNone(accounts.plan(cfg, datetime(2026, 11, 28, 9, tzinfo=accounts.KST))["series"])


class RichupComplianceTest(unittest.TestCase):
    def setUp(self):
        self.cfg = accounts.load("richup")

    def blocked(self, **patch):
        s = sample(); s.update(patch)
        return compliance.has_block(compliance.check(s, self.cfg))

    def test_sample_passes(self):
        self.assertFalse(compliance.has_block(compliance.check(sample(), self.cfg)))

    def test_company_name_blocked(self):
        self.assertTrue(self.blocked(caption="굿리치 리치업지점이 알려드립니다"))
        self.assertTrue(self.blocked(hashtags=["#GoodRich"]))

    def test_insurance_claims_blocked(self):
        for t in ["실손은 무조건 보장됩니다", "최저 보험료 비교", "지금 해지하고 갈아타세요",
                  "댓글로 병력 남겨주세요", "보험금 꼼수 공개"]:
            self.assertTrue(self.blocked(title=t), t)

    def test_recruiting_income_blocked(self):
        self.assertTrue(self.blocked(summary="신입도 월 500만원 보장"))

    def test_insurer_name_only_warns(self):
        res = compliance.check({**sample(), "hook": "삼성화재 약관에서도"}, self.cfg)
        self.assertFalse(compliance.has_block(res))
        self.assertTrue(any(lv == "warn" for lv, _, _ in res))


class EngineTest(unittest.TestCase):
    def test_prompt_contains_account_rules(self):
        cfg = accounts.load("richup")
        p = draft.build_prompt("소멸시효", "사실", cfg, "보험금 청구 꿀팁")
        self.assertIn("리치업지점", p)
        self.assertIn("굿리치", p)  # 금지 규칙 문장으로 들어감
        self.assertIn("보험금 청구 꿀팁", p)

    def test_caption_has_required_notice(self):
        cfg = accounts.load("richup")
        cap = render.caption_text(sample(), cfg)
        for phrase in cfg["required_caption"] + [cfg["disclaimer"]]:
            self.assertIn(phrase, cap)

    def test_render_cards(self):
        cfg = accounts.load("richup")
        with tempfile.TemporaryDirectory() as d:
            made = render.render(sample(), cfg, d, reel=False)
            self.assertEqual(len(list(Path(d, "cards").glob("*.png"))), len(sample()["slides"]) + 2)
            self.assertTrue(any(str(m).endswith("caption.txt") for m in made))


if __name__ == "__main__":
    unittest.main()


def test_narration_and_remote_request(tmp_path):
    import base64, json as _j
    from contentagent import accounts as _a, voice as _v, remote as _r
    cfg = _a.load("richup")
    src = Path(__file__).resolve().parents[1] / "agents/content/examples/richup/script.json"
    script = _j.loads(src.read_text(encoding="utf-8"))
    lines = _v.narration(script, cfg)
    assert len(lines) == len(script["slides"]) + 2
    d = tmp_path / "2026-11-25_테스트"; d.mkdir()
    (d / "script.json").write_bytes(src.read_bytes())
    req = _j.loads(_r.request("richup", d / "script.json"))
    assert req["inputs"]["folder"] == "2026-11-25_테스트"
    assert _j.loads(base64.b64decode(req["inputs"]["script_b64"]))["title"] == script["title"]
