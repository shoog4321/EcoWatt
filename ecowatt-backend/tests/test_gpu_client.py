"""Retry rules of the GPU client with a fake HTTP layer.  Run:  python -m tests.test_gpu_client"""
import asyncio
import types

from tests import _httpx_stub  # noqa: F401
import httpx

from app import gpu_client
from app.advice_engine import AdviceGenerationError
from app.gpu_client import GpuClient
from app.llm_client import LLMUnavailable


class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._p, self.text = status, payload, text or str(payload)

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


class FakeHttp:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    async def post(self, url, json=None, headers=None, timeout=None, files=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "files": files})
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    async def get(self, url, headers=None, timeout=None):
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


def client(http, url="https://gpu.example"):
    s = types.SimpleNamespace(llm_base_url=url, llm_api_key="k", llm_timeout_s=5)
    return GpuClient(http, s)


async def _no_sleep(_):  # keep tests fast
    return None


gpu_client.asyncio.sleep = _no_sleep


def call(http, **kw):
    return asyncio.run(client(http, **kw).generate({"a": 1}, {"m": 1}, {"x": 2}))


def raises(exc, http, **kw):
    try:
        call(http, **kw)
    except exc as e:
        return e
    raise AssertionError(f"expected {exc.__name__}")


def test_success_sends_key_and_tunnel_header():
    http = FakeHttp(Resp(200, {"advice": []}))
    assert call(http) == {"advice": []}
    c = http.calls[0]
    assert c["url"] == "https://gpu.example/generate" and c["headers"]["Authorization"] == "Bearer k"
    assert c["headers"]["ngrok-skip-browser-warning"] == "true" and set(c["json"]) == {"profile", "period", "analysis", "exclude_ids"}


def test_tunnel_down_retries_then_unavailable():
    http = FakeHttp(httpx.ConnectError("x"), Resp(404, None, "ngrok offline"), Resp(502, None))
    raises(LLMUnavailable, http)
    assert len(http.calls) == 3


def test_recovers_after_transient_failure():
    assert call(FakeHttp(Resp(503, {"error": "gpu_out_of_memory"}), Resp(200, {"advice": [1]}))) == {"advice": [1]}


def test_read_timeout_is_not_retried():
    http = FakeHttp(httpx.ReadTimeout("slow"))
    raises(LLMUnavailable, http)
    assert len(http.calls) == 1


def test_model_output_error_is_a_content_failure_not_an_outage():
    raises(AdviceGenerationError, FakeHttp(Resp(422, {"error": "model_invalid_output", "detail": "bad json"})))


def test_plain_422_is_a_request_bug_not_a_content_failure():
    e = raises(LLMUnavailable, FakeHttp(Resp(422, {"detail": [{"msg": "field required"}]})))
    assert "422" in str(e)


def test_wrong_key_and_unconfigured_url():
    assert "API key" in str(raises(LLMUnavailable, FakeHttp(Resp(401, {"detail": "Invalid API key"}))))
    raises(LLMUnavailable, FakeHttp(), url="")


def test_ping_uses_health_info():
    assert asyncio.run(client(FakeHttp(Resp(200, {"status": "ok"}))).ping()) is True
    assert asyncio.run(client(FakeHttp(httpx.ConnectError("x"))).ping()) is False


def test_ocr_on_gpu_and_fallback_signals():
    http = FakeHttp(Resp(200, {"success": True, "amount_due": 516.14}))
    out = asyncio.run(client(http).ocr(b"img", "bill.png"))
    assert out["amount_due"] == 516.14 and http.calls[0]["url"].endswith("/ocr")
    assert http.calls[0]["files"] == {"file": ("bill.png", b"img")}
    # GPU without OCR / tunnel down / unreachable -> None, so the backend scans on the CPU instead
    for outcome in (Resp(404, {}), Resp(503, {"detail": "no ocr"}), httpx.ConnectError("down")):
        assert asyncio.run(client(FakeHttp(outcome)).ocr(b"img", "b.png")) is None
    assert asyncio.run(client(FakeHttp(), url="").ocr(b"img", "b.png")) is None
    # a bad image is the user's problem, not an outage
    try:
        asyncio.run(client(FakeHttp(Resp(400, {"detail": "Please upload a valid JPG or PNG image."}))).ocr(b"x", "b"))
        assert False
    except ValueError as e:
        assert "valid JPG" in str(e)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
