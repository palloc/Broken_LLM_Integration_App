import pytest

from app.llm_shell_chain import PythonCodeOutputParser
from app import llm_shell_chain


@pytest.mark.parametrize("language", ["python", ""])
def test_parse_fenced_python(language):
    code = "def solution():\n    return 'hello'"
    parsed = PythonCodeOutputParser().parse(f"```{language}\n{code}\n```")
    assert parsed == code
    compile(parsed, "<generated>", "exec")


def test_preserve_raw_python():
    code = "import os\n\ndef solution():\n    return os.name\n"
    assert PythonCodeOutputParser().parse(code) == code


def test_preserve_non_code_response():
    text = "Prompt Attack Detected."
    assert PythonCodeOutputParser().parse(text) == text


def test_pal_uses_explicit_globals():
    llm_shell_chain.PALChain.reset_mock()
    llm_shell_chain.create_pal_chain_native("test prompt")
    assert llm_shell_chain.PALChain.call_args.kwargs["python_globals"] == {}