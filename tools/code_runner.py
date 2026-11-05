"""Sandboxed Python code execution tool with safety timeouts and guardrails."""

import subprocess
import sys
import tempfile
from pathlib import Path

from tools.registry import register_tool

DANGEROUS_PATTERNS = [
    "shutil.rmtree",
    "os.system('rm",
    "os.system(\"rm",
    "format c:",
    "del /f /s /q",
    "rmdir /s /q",
    ":(){ :|:& };:",
    "reg delete",
]


@register_tool(
    name="execute_python_code",
    description="Executes a Python code snippet locally in an isolated subprocess and returns the printed output (stdout/stderr)."
)
def execute_python_code(code: str) -> str:
    """Safely runs Python code with an 8-second execution timeout."""
    # Safety guardrails
    lower_code = code.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in lower_code:
            return f"Execution blocked: Potential destructive system pattern detected ('{pattern}')."

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
        temp_path = temp_file.name
        temp_file.write(code)

    try:
        proc = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=8.0
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return f"Execution failed (Exit Code {proc.returncode}):\n{stderr or stdout}"

        return stdout if stdout else "Code executed successfully with zero output."

    except subprocess.TimeoutExpired:
        return "Execution terminated: Operation timed out after 8 seconds."
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
