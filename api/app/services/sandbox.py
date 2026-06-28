from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass

from app.config import settings


@dataclass
class SandboxRun:
    engine: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_seconds: float = 0.0
    used_fallback: bool = False


def extract_python_blocks(markdown: str) -> list[str]:
    pattern = r"```(?:python|py)?\s*\n(.*?)```"
    blocks = re.findall(pattern, markdown, re.DOTALL | re.IGNORECASE)
    return [block.strip() for block in blocks if block.strip()]


def verify_code(
    code: str,
    *,
    engine: str | None = None,
    timeout_seconds: int | None = None,
) -> SandboxRun:
    requested_engine = engine or settings.sandbox_engine
    timeout = timeout_seconds or settings.modal_timeout_seconds
    if requested_engine == "local":
        return _run_local(code, timeout)

    should_try_modal = requested_engine == "modal" or (
        requested_engine == "auto" and settings.modal_enabled
    )
    if not should_try_modal:
        return _run_local(code, timeout)

    try:
        return _run_modal(code, timeout)
    except Exception as exc:
        if requested_engine == "modal":
            return SandboxRun(
                engine="modal",
                success=False,
                stderr=f"Modal sandbox failed: {exc}",
                exit_code=None,
                duration_seconds=0.0,
            )
        fallback = _run_local(code, timeout)
        fallback.used_fallback = True
        fallback.stderr = (
            f"Modal unavailable, used local fallback instead: {exc}\n"
            f"{fallback.stderr}"
        ).strip()
        return fallback


def _run_local(code: str, timeout_seconds: int) -> SandboxRun:
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.getenv("TEMP", "/tmp"),
                "PYTHONNOUSERSITE": "1",
            },
        )
        duration = time.perf_counter() - start
        return SandboxRun(
            engine="local",
            success=proc.returncode == 0,
            stdout=proc.stdout[-4000:],
            stderr=proc.stderr[-4000:],
            exit_code=proc.returncode,
            duration_seconds=duration,
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxRun(
            engine="local",
            success=False,
            stdout=(exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            stderr=f"TIMEOUT after {timeout_seconds}s",
            exit_code=None,
            duration_seconds=float(timeout_seconds),
        )


def _run_modal(code: str, timeout_seconds: int) -> SandboxRun:
    import modal

    start = time.perf_counter()
    app = modal.App.lookup(settings.modal_app_name, create_if_missing=True)
    image = modal.Image.debian_slim(python_version="3.11")
    sandbox = modal.Sandbox.create(
        app=app,
        image=image,
        timeout=timeout_seconds + 30,
        block_network=True,
    )
    try:
        process = sandbox.exec("python", "-I", "-c", code, timeout=timeout_seconds)
        stdout = process.stdout.read() or ""
        stderr = process.stderr.read() or ""
        wait_result = process.wait()
        exit_code = wait_result if isinstance(wait_result, int) else getattr(process, "returncode", None)
        duration = time.perf_counter() - start
        return SandboxRun(
            engine="modal",
            success=exit_code == 0,
            stdout=stdout[-4000:],
            stderr=stderr[-4000:],
            exit_code=exit_code,
            duration_seconds=duration,
        )
    finally:
        try:
            sandbox.terminate()
        finally:
            sandbox.detach()
