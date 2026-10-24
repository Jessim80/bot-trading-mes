from src.ai import APIError, ask, is_retryable

CFG = {"enabled": True, "max_retries": 2,
       "models": [{"provider": "gemini", "model": "A"}, {"provider": "gemini", "model": "B"}]}


class Script:
    def __init__(self, steps):
        self.steps, self.calls = list(steps), []

    def __call__(self, model, system, prompt, timeout):
        self.calls.append(model)
        x = self.steps.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


def test_retry_then_success():
    sleeps, c = [], Script([APIError(429), APIError(503), "ok"])
    assert ask("s", "p", CFG, call=c, sleep=sleeps.append) == "ok"
    assert c.calls == ["A", "A", "A"] and len(sleeps) == 2


def test_dead_model_falls_back():
    c = Script([APIError(404, "model not found"), "secours"])
    assert ask("s", "p", CFG, call=c, sleep=lambda s: None) == "secours" and c.calls == ["A", "B"]


def test_all_fail_returns_none():
    c = Script([APIError(500)] * 3 + [TimeoutError()] * 3)
    assert ask("s", "p", CFG, call=c, sleep=lambda s: None) is None and c.calls == ["A"] * 3 + ["B"] * 3


def test_no_key_means_no_ai_and_no_cost():
    assert ask("s", "p", CFG, env={}) is None


def test_retry_after_is_honored():
    sleeps = []
    assert ask("s", "p", CFG, call=Script([APIError(429, retry_after=7.0), "ok"]), sleep=sleeps.append) == "ok"
    assert sleeps == [7.0]


def test_classification():
    assert is_retryable(APIError(503)) and not is_retryable(APIError(401)) and is_retryable(ConnectionError())
