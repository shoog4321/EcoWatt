"""GPU wrapper logic with a fake engine (no torch / fastapi).  Run:  python -m tests.test_gpu_service"""
import asyncio
import hashlib
import tempfile
import threading
import time
from pathlib import Path

from gpu_service.service import EngineService, GpuBusy, ModelOutputError, strip_personal


class FakeEngine:
    model_id = "Qwen/Qwen3-4B-Instruct-2507"

    def __init__(self, behaviour=None, delay=0.0):
        self.behaviour, self.delay, self.seen = behaviour, delay, []
        self.catalog = [{"advice_id": f"ADV_{n:03d}"} for n in range(1, 8)]
        self.catalog_seen = []
        self.active = self.max_active = 0
        self._m = threading.Lock()

    def generate_advice(self, profile, period, analysis):
        with self._m:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.seen.append(profile)
            self.catalog_seen.append([a["advice_id"] for a in self.catalog])
            time.sleep(self.delay)
            if isinstance(self.behaviour, Exception):
                raise self.behaviour
            return [{"advice_id": "ADV_001", "personalized_advice": "Set the AC to 24."},
                    {"advice_id": "ADV_009", "personalized_advice": "Check the unit size."}]
        finally:
            with self._m:
                self.active -= 1

    def _safe(self, aid, text):
        return aid != "ADV_009"          # pretend ADV_009 lost its safety condition


def service(engine):
    d = Path(tempfile.mkdtemp())
    (d / "advice_catalog.json").write_text('[{"advice_id": "ADV_001"}]')
    return EngineService(engine, d), d


def test_personal_data_never_reaches_engine():
    eng = FakeEngine()
    svc, _ = service(eng)
    asyncio.run(svc.generate({"region": "Riyadh", "first_name": "Sara", "lastName": "X", "user_id": "u"}, {}, {}))
    assert eng.seen[0] == {"region": "Riyadh"}
    assert strip_personal({"Email": "a@b.c", "acType": "Split"}) == {"acType": "Split"}


def test_audit_flags_unsafe_items_and_hashes_are_reported():
    svc, d = service(FakeEngine())
    out = asyncio.run(svc.generate({}, {}, {}))
    assert {a["advice_id"]: a["safe"] for a in out["audit"]} == {"ADV_001": True, "ADV_009": False}
    assert out["catalog_sha256"] == hashlib.sha256((d / "advice_catalog.json").read_bytes()).hexdigest()
    assert out["prompt_sha256"] is None                       # file absent -> reported as None, not a crash
    assert svc.health()["model"] == "Qwen/Qwen3-4B-Instruct-2507"


def test_requests_are_serialised_on_the_gpu():
    eng = FakeEngine(delay=0.05)
    svc, _ = service(eng)

    async def go():
        await asyncio.gather(*(svc.generate({}, {}, {}) for _ in range(4)))

    asyncio.run(go())
    assert eng.max_active == 1 and len(eng.seen) == 4


def test_error_mapping():
    for exc, expected in ((ValueError("Model produced invalid JSON: x"), ModelOutputError),
                          (RuntimeError("CUDA out of memory. Tried to allocate"), GpuBusy)):
        svc, _ = service(FakeEngine(behaviour=exc))
        try:
            asyncio.run(svc.generate({}, {}, {}))
            raise AssertionError("expected error")
        except expected:
            pass
    svc, _ = service(FakeEngine(behaviour=RuntimeError("something else")))
    try:
        asyncio.run(svc.generate({}, {}, {}))
        raise AssertionError("expected RuntimeError")
    except (ModelOutputError, GpuBusy):
        raise AssertionError("unrelated RuntimeError must not be mapped")
    except RuntimeError:
        pass


def test_excluded_ids_hidden_for_one_request_only():
    eng = FakeEngine()
    svc, _ = service(eng)
    asyncio.run(svc.generate({}, {}, {}, ["ADV_002", "ADV_005"]))
    asyncio.run(svc.generate({}, {}, {}))
    assert eng.catalog_seen[0] == ["ADV_001", "ADV_003", "ADV_004", "ADV_006", "ADV_007"]
    assert len(eng.catalog_seen[1]) == 7 and len(eng.catalog) == 7


def test_scan_bill_uses_ocr_and_cleans_up():
    seen = {}

    def fake_ocr(path):
        seen["path"] = path
        seen["bytes"] = Path(path).read_bytes()
        return {"success": True, "amount_due": 516.14}

    svc, _ = service(FakeEngine())
    svc.ocr = fake_ocr
    out = asyncio.run(svc.scan_bill(b"\x89PNG...", ".png"))
    assert out["amount_due"] == 516.14 and seen["bytes"] == b"\x89PNG..." and not Path(seen["path"]).exists()
    assert svc.health()["ocr"] is True


def test_scan_bill_without_ocr_is_an_error():
    svc, _ = service(FakeEngine())
    try:
        asyncio.run(svc.scan_bill(b"x", ".png"))
        assert False
    except RuntimeError as e:
        assert "not available" in str(e)
    assert svc.health()["ocr"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
