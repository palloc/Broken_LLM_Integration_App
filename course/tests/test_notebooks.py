import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["course", "student_workspace"])
def sql_ask(request):
    notebook = json.loads((ROOT / request.param / "notebooks/20_p2sql.ipynb").read_text())
    source = next(
        "".join(cell["source"]) for cell in notebook["cells"]
        if cell["cell_type"] == "code" and "def ask(" in "".join(cell["source"])
    )
    namespace = {"launcher": SimpleNamespace(active_port=lambda: 8000)}
    exec(compile(source, "<notebook ask>", "exec"), namespace)
    return namespace["ask"]


def test_sql_display_preserves_execution_evidence(sql_ask, monkeypatch):
    evidence = "SQLQuery: UPDATE users\nSET email = 'test@example.com'\nWHERE username = 'admin';\nSQLResult: "
    response = Mock()
    response.json.return_value = {"text": evidence + "\nAnswer: SQLQuery: SELECT unrelated FROM messages"}
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    assert sql_ask("p2sql-injection-lv1", "question") == evidence


@pytest.mark.parametrize("text, expected", [
    ("Error: Blocked by input filter. (Potential malicious request)",
     "Error: Blocked by input filter. (Potential malicious request)"),
    ("SQLQuery: REFUSE\nAnswer: REFUSE", "SQLQuery: REFUSE"),
])
def test_sql_display_preserves_status_response(sql_ask, monkeypatch, text, expected):
    response = Mock()
    response.json.return_value = {"text": text}
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    assert sql_ask("p2sql-injection-lv2", "question") == expected


def test_sql_display_reports_http_error(sql_ask, monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("503 unavailable")
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(requests.HTTPError, match="503"):
        sql_ask("p2sql-injection-lv1", "question")
    response.json.assert_not_called()


@pytest.mark.parametrize("name", ["10_prompt_leaking.ipynb", "20_p2sql.ipynb", "30_llm4shell.ipynb"])
def test_distributed_notebook_matches_source(name):
    source = json.loads((ROOT / "course/notebooks" / name).read_text())
    distributed = json.loads((ROOT / "student_workspace/notebooks" / name).read_text())
    source_cells = [(cell["cell_type"], "".join(cell["source"])) for cell in source["cells"]]
    assert source_cells == [(cell["cell_type"], "".join(cell["source"])) for cell in distributed["cells"]]
    for cell_type, code in source_cells:
        if cell_type == "code":
            compile(code, name, "exec")


@pytest.mark.parametrize("directory", ["course", "student_workspace"])
@pytest.mark.parametrize("outcome", ["changed", "wrong_user", "refused", "already_changed"])
def test_tampering_checks_actual_admin_value(directory, outcome, tmp_path, monkeypatch, capsys):
    database_path = tmp_path / "lesson.db"
    initial = "attacker@example.com" if outcome == "already_changed" else "admin@example.com"
    with sqlite3.connect(database_path) as database:
        database.execute("CREATE TABLE users (username TEXT, email TEXT)")
        database.executemany("INSERT INTO users VALUES (?, ?)", [("admin", initial), ("alice", "alice@example.com")])

    def ask(mode, question):
        if outcome in ("changed", "wrong_user"):
            username = "admin" if outcome == "changed" else "alice"
            with sqlite3.connect(database_path) as database:
                database.execute("UPDATE users SET email = ? WHERE username = ?", ("attacker@example.com", username))
        return "SQLQuery: UPDATE users SET email = 'attacker@example.com'"

    monkeypatch.setitem(sys.modules, "broken_handson.config", SimpleNamespace(PATHS=SimpleNamespace(db_path=database_path)))
    notebook = json.loads((ROOT / directory / "notebooks/20_p2sql.ipynb").read_text())
    source = next("".join(cell["source"]) for cell in notebook["cells"]
                  if cell["cell_type"] == "code" and "Set admin's email" in "".join(cell["source"]))
    exec(compile(source, "<tampering cell>", "exec"), {"ask": ask})
    output = capsys.readouterr().out
    if outcome == "changed":
        assert "改ざん成功" in output
    elif outcome == "already_changed":
        assert "実行前から変更済み" in output
    else:
        assert "改ざんは確認できませんでした" in output