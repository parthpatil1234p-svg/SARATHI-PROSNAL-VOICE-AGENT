"""Autonomous Error Resolver and Developer Agent for S.A.R.A.T.H.I.

Inspired by Mark-LVI's actions/dev_agent.py and core/code_checks.py:
- Classifies and diagnoses Python, OS, syntax, and dependency errors.
- Automatically installs missing Python packages via pip/uv.
- Parses tracebacks down to exact file:line spans.
- Self-healing code executor: executes code, catches runtime/import errors, heals the environment, and re-executes.
- Integrated with core/undo.py for instant rollback.
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR
from core.outcome import done, failed, unverified
from core.undo import undo_manager
from tools.registry import register_tool

logger = logging.getLogger("SARATHI.DevAgent")


def parse_traceback(output: str) -> list[tuple[str, int, str]]:
    """Extracts (file_path, line_number, code_snippet) tuples from a Python traceback."""
    pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)(?:,\s+in\s+([^\n]+))?', re.IGNORECASE)
    matches = []
    for match in pattern.finditer(output):
        raw_path = match.group(1)
        line_num = int(match.group(2))
        func_name = match.group(3) or "module"
        matches.append((raw_path, line_num, func_name))
    return matches


def classify_error(output: str) -> dict[str, Any]:
    """Analyzes stderr/stdout to classify the error type and relevant metadata."""
    low = output.lower()

    # 1. Dependency / Module Missing
    dep_match = re.search(r"(?:No module named|ModuleNotFoundError: No module named|ImportError: cannot import name)\s+['\"]?([a-zA-Z0-9_\.]+)['\"]?", output)
    if dep_match:
        module_name = dep_match.group(1).split(".")[0]
        return {
            "type": "dependency_error",
            "module": module_name,
            "description": f"Missing module '{module_name}'"
        }

    # 2. Syntax / AST Parse Error
    if "syntaxerror" in low or "invalid syntax" in low or "unmatched" in low:
        return {
            "type": "syntax_error",
            "description": "Python syntax parsing error"
        }

    # 3. Indentation Error
    if "indentationerror" in low or "taberror" in low:
        return {
            "type": "indentation_error",
            "description": "Python indentation or mixed tabs/spaces error"
        }

    # 4. File Not Found
    fnf_match = re.search(r"FileNotFoundError:.*['\"]([^'\"]+)['\"]", output)
    if fnf_match:
        return {
            "type": "file_not_found",
            "path": fnf_match.group(1),
            "description": f"Target file or path '{fnf_match.group(1)}' not found"
        }

    # 5. Permission / Access Denied
    if "permissionerror" in low or "access is denied" in low:
        return {
            "type": "permission_error",
            "description": "OS permission denied"
        }

    # 6. Generic Runtime Error
    err_match = re.search(r"([A-Za-z0-9_]+Error):\s*([^\n]+)", output)
    if err_match:
        return {
            "type": "runtime_error",
            "error_class": err_match.group(1),
            "details": err_match.group(2).strip(),
            "description": f"{err_match.group(1)}: {err_match.group(2).strip()}"
        }

    return {
        "type": "unknown_error",
        "description": "Unclassified error output"
    }


def auto_install_package(package_name: str) -> tuple[bool, str]:
    """Installs a missing package using the current virtualenv Python."""
    # Mapping common import names to pip distribution names
    PKG_MAP = {
        "cv2": "opencv-python",
        "PIL": "pillow",
        "sklearn": "scikit-learn",
        "yaml": "pyyaml",
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "sounddevice": "sounddevice",
        "soundfile": "soundfile",
        "numpy": "numpy",
        "groq": "groq",
    }
    dist_name = PKG_MAP.get(package_name, package_name)
    py_exec = sys.executable

    logger.info(f"Attempting autonomous package installation: {dist_name} using {py_exec}")
    try:
        cmd = [py_exec, "-m", "pip", "install", dist_name, "--quiet"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode == 0:
            logger.info(f"Successfully installed package: {dist_name}")
            return True, f"Successfully installed '{dist_name}'"
        return False, f"pip install failed (code {res.returncode}): {res.stderr.strip()}"
    except Exception as e:
        return False, f"Installation exception: {e}"


@register_tool(
    name="analyze_and_fix_error",
    description="Analyzes an error message or Python traceback, diagnoses root cause, automatically installs missing packages, or patches broken syntax."
)
def analyze_and_fix_error(error_text: str, file_path: str = "") -> str:
    """Diagnoses and autonomously attempts to heal the reported error."""
    if not error_text or not error_text.strip():
        return failed("analyze_error", "Empty error text provided")

    classification = classify_error(error_text)
    err_type = classification["type"]
    tb_matches = parse_traceback(error_text)

    # 1. Autonomous Dependency Resolution
    if err_type == "dependency_error":
        module_name = classification.get("module")
        if module_name:
            success, msg = auto_install_package(module_name)
            if success:
                return done(
                    "resolve_dependency",
                    module=module_name,
                    resolution=msg,
                    verified=True
                )
            return failed("resolve_dependency", msg, module=module_name)

    # 2. Syntax / Indentation Healing
    target_file = None
    if file_path and Path(file_path).exists():
        target_file = Path(file_path)
    elif tb_matches:
        for p, line_no, _ in reversed(tb_matches):
            cand = Path(p)
            if cand.exists() and cand.is_file():
                target_file = cand
                break

    if target_file and err_type in ("syntax_error", "indentation_error"):
        try:
            undo_manager.snapshot(target_file, f"Pre-heal snapshot before fixing {err_type}")
            content = target_file.read_text(encoding="utf-8", errors="replace")

            # Check if simple AST parse can locate line
            try:
                ast.parse(content)
                return done(
                    "verify_syntax",
                    file=str(target_file.name),
                    note="File AST parsed cleanly without syntax errors"
                )
            except SyntaxError as syn_err:
                # If mixed tabs/spaces, normalize to 4 spaces
                lines = content.splitlines()
                fixed_lines = [l.replace("\t", "    ") for l in lines]
                fixed_content = "\n".join(fixed_lines) + "\n"

                try:
                    ast.parse(fixed_content)
                    target_file.write_text(fixed_content, encoding="utf-8")
                    return done(
                        "heal_syntax",
                        file=str(target_file.name),
                        action="normalized_indentation",
                        fixed_line=syn_err.lineno
                    )
                except SyntaxError:
                    return unverified(
                        "heal_syntax",
                        file=str(target_file.name),
                        line=syn_err.lineno,
                        details=str(syn_err.msg),
                        diagnostic="Manual logic or syntax edit required around line " + str(syn_err.lineno)
                    )
        except Exception as e:
            return failed("heal_file", str(e), file=str(target_file))

    # 3. Informative Diagnostic Report
    return done(
        "diagnose_error",
        error_type=err_type,
        summary=classification["description"],
        traceback_depth=len(tb_matches)
    )


@register_tool(
    name="execute_and_heal_code",
    description="Executes a Python code snippet in an isolated subprocess. If errors or missing packages occur, autonomously resolves them and re-runs."
)
def execute_and_heal_code(code: str, timeout_sec: int = 15) -> str:
    """Executes code, catches errors, applies autonomous healing, and verifies success."""
    cleaned_code = code.strip()
    if not cleaned_code:
        return failed("execute_code", "No code provided")

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        temp_file = Path(tf.name)
        tf.write(cleaned_code)

    py_exec = sys.executable
    max_attempts = 3
    current_attempt = 1

    try:
        while current_attempt <= max_attempts:
            logger.info(f"Executing code snippet (attempt {current_attempt}/{max_attempts})...")
            try:
                res = subprocess.run(
                    [py_exec, str(temp_file)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec
                )
            except subprocess.TimeoutExpired:
                return failed("execute_code", f"Execution timed out after {timeout_sec}s", attempt=current_attempt)

            if res.returncode == 0:
                output = res.stdout.strip()
                return done(
                    "execute_code",
                    stdout=output or "(Executed with 0 exit code and no stdout)",
                    attempts=current_attempt,
                    verified=True
                )

            # Execution failed with non-zero exit code: diagnose error
            combined_err = (res.stderr or res.stdout).strip()
            classification = classify_error(combined_err)

            if classification["type"] == "dependency_error":
                mod = classification.get("module")
                if mod:
                    logger.info(f"Self-healing: Missing module '{mod}' detected. Installing...")
                    inst_ok, inst_msg = auto_install_package(mod)
                    if inst_ok:
                        current_attempt += 1
                        continue  # Re-run code after installation

            # Return failed outcome if not auto-healable
            return failed(
                "execute_code",
                reason=f"Code returned exit code {res.returncode}",
                stderr=combined_err[:500],
                classification=classification["type"]
            )

        return failed("execute_code", "Max self-healing attempts exceeded", attempts=max_attempts)
    finally:
        temp_file.unlink(missing_ok=True)


@register_tool(
    name="undo_last_change",
    description="Reverts the most recent file change or deletion made by Sarathi."
)
def undo_last_change() -> str:
    """Restores the previous file state using the undo manager."""
    success, msg = undo_manager.undo_last()
    if success:
        return done("undo", message=msg)
    return failed("undo", msg)


__all__ = [
    "parse_traceback",
    "classify_error",
    "auto_install_package",
    "analyze_and_fix_error",
    "execute_and_heal_code",
    "undo_last_change"
]
