import sqlite3

import pytest

from unittest.mock import MagicMock

from app import llm_db_chain
from app.llm_db_chain import SQLCodeOutputParser, SQLGenerationRefused


@pytest.mark.parametrize("language", ["sql", ""])
def test_parse_fenced_sql(language):
    query = "SELECT 42"
    parsed = SQLCodeOutputParser().parse(f"```{language}\n{query}\n```")
    with sqlite3.connect(":memory:") as database:
        assert database.execute(parsed).fetchone() == (42,)


@pytest.mark.parametrize("text", ["SELECT 42", "UPDATE users SET email = 'test@example.com'", "Prompt Attack Detected."])
def test_preserve_unfenced_response(text):
    assert SQLCodeOutputParser().parse(text) == text


@pytest.mark.parametrize("text", ["REFUSE", "SQLQuery: REFUSE", "```sql\nREFUSE\n```"])
def test_refusal_is_not_sql(text):
    with pytest.raises(SQLGenerationRefused):
        SQLCodeOutputParser().parse(text)


def test_return_actual_sql_result(monkeypatch):
    chain = MagicMock()
    chain.invoke.return_value = {
        "result": "A model answer",
        "intermediate_steps": [{}, "SELECT 42", {"sql_cmd": "SELECT 42"}, "[(42,)]"],
    }
    monkeypatch.setattr(llm_db_chain, "create_db_chain", lambda: chain)
    assert llm_db_chain.run_sql_chain("question") == "SQLQuery: SELECT 42\nSQLResult: [(42,)]\nAnswer: A model answer"


def test_return_refusal_without_database_error(monkeypatch):
    chain = MagicMock()
    chain.invoke.side_effect = SQLGenerationRefused("REFUSE")
    monkeypatch.setattr(llm_db_chain, "create_db_chain", lambda: chain)
    assert llm_db_chain.run_sql_chain("question") == "SQLQuery: REFUSE\nAnswer: REFUSE"


@pytest.mark.parametrize("verbose", [False, True])
def test_sql_chain_respects_verbose_setting(monkeypatch, verbose):
    factory = MagicMock()
    monkeypatch.setattr(llm_db_chain, "SQLDatabaseChain", factory)
    monkeypatch.setattr(llm_db_chain.settings, "SQL_CHAIN_VERBOSE", verbose)
    llm_db_chain.create_db_chain()
    assert factory.from_llm.call_args.kwargs["verbose"] is verbose