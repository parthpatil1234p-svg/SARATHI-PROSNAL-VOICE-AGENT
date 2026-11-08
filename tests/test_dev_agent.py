"""Unit tests for Autonomous Error Resolver and Dev Agent capabilities."""

import os
import tempfile
from pathlib import Path
import pytest

from core.outcome import done, failed, unverified, DONE, FAILED, UNVERIFIED
from core.undo import UndoManager
from tools.dev_agent import parse_traceback, classify_error, analyze_and_fix_error, execute_and_heal_code
from tools.app_controller import list_running_applications
from tools.file_controller import write_file_verified, read_file_snippet, delete_file_safely


def test_outcome_formatting():
    """Verifies structured fact output format."""
    d = done("open_app", app="spotify", pid=1234)
    assert "status=done" in d
    assert "action=open_app" in d
    assert "app=spotify" in d
    assert "pid=1234" in d

    f = failed("open_app", "Process crashed", app="notepad")
    assert "status=failed" in f
    assert 'reason="Process crashed"' in f or "reason=Process" in f


def test_traceback_parsing():
    """Verifies parsing of standard Python tracebacks."""
    sample_tb = '''
Traceback (most recent call last):
  File "P:\\Startup\\test_sample.py", line 42, in my_function
    res = 1 / 0
ZeroDivisionError: division by zero
'''
    matches = parse_traceback(sample_tb)
    assert len(matches) == 1
    file_path, line_no, func_name = matches[0]
    assert line_no == 42
    assert "test_sample.py" in file_path
    assert func_name == "my_function"


def test_error_classification():
    """Verifies error classification for dependencies, syntax, and runtime."""
    dep_err = "ModuleNotFoundError: No module named 'scipy'"
    c1 = classify_error(dep_err)
    assert c1["type"] == "dependency_error"
    assert c1["module"] == "scipy"

    syn_err = "SyntaxError: invalid syntax"
    c2 = classify_error(syn_err)
    assert c2["type"] == "syntax_error"

    fnf_err = "FileNotFoundError: [Errno 2] No such file or directory: 'data.csv'"
    c3 = classify_error(fnf_err)
    assert c3["type"] == "file_not_found"


def test_undo_manager():
    """Verifies transactional snapshot and rollback of file changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_backup = Path(tmpdir) / "backup"
        mgr = UndoManager(backup_dir=tmp_backup)

        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("initial version", encoding="utf-8")

        # Take snapshot and modify
        mgr.snapshot(test_file, "modify initial")
        test_file.write_text("corrupted version", encoding="utf-8")
        assert test_file.read_text(encoding="utf-8") == "corrupted version"

        # Undo
        success, msg = mgr.undo_last()
        assert success is True
        assert test_file.read_text(encoding="utf-8") == "initial version"


def test_execute_and_heal_code_success():
    """Verifies clean execution of valid Python code."""
    code = "x = 10 + 20\nprint(f'RESULT={x}')"
    out = execute_and_heal_code(code)
    assert "status=done" in out
    assert "RESULT=30" in out


def test_file_controller_verified():
    """Verifies safe file operations with syntax check and undo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "sample_code.py"
        res = write_file_verified(str(target), "def hello():\n    return 'world'\n")
        assert "status=done" in res
        assert target.exists()

        # Read snippet
        read_res = read_file_snippet(str(target))
        assert "status=done" in read_res
        assert "hello()" in read_res


def test_list_running_applications():
    """Verifies listing active desktop processes."""
    res = list_running_applications(limit=5)
    assert "status=done" in res
    assert "action=list_apps" in res
