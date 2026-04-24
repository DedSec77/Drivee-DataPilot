from app.core.llm import LlamaCppLLM, LLMRouter, _parse_model_output


def test_construct_llm():
    llm = LlamaCppLLM(
        base_url="http://localhost:8080/v1",
        model="qwen",
        api_key="sk-no-key",
        timeout_s=5,
        max_tokens=256,
    )
    assert llm.model == "qwen"
    assert llm.base_url.endswith("/v1")


def test_parse_json_answer():
    raw = '{"sql": "SELECT 1", "used_metrics": ["trips_total"], "confidence": 0.9}'
    cand = _parse_model_output(raw)
    assert cand.sql == "SELECT 1"
    assert cand.used_metrics == ["trips_total"]
    assert cand.confidence == 0.9
    assert cand.clarify is None


def test_parse_json_clarify():
    cand = _parse_model_output('{"clarify": "metric ambiguous"}')
    assert cand.sql is None
    assert cand.clarify == "metric ambiguous"


def test_parse_sql_only():
    cand = _parse_model_output("SELECT count(*) FROM fct_trips WHERE 1=1")
    assert cand.sql is not None
    assert "fct_trips" in cand.sql


def test_parse_fenced_sql():
    raw = "Here is your query:\n```sql\nSELECT 42\n```\nenjoy"
    cand = _parse_model_output(raw)
    assert cand.sql == "SELECT 42"


def test_router_constructs():
    r = LLMRouter()
    assert r.primary.model != ""
