"""obkit hooks: one setup's answer per company, what the setups see first, and the request each setup sends."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from unittest import mock

from judge.grader import grade_stage

from . import http_client, registry
from .adapters._extraction import user_content
from .adapters._research import HttpError
from .models import FIELDS, Company
from .question import SEARCH_EXTRACTION_PROMPT, OUTPUT_SCHEMA, instruction
from .runner import _Pacer

PROBE_COMPANY = Company("example.com", "Example Company")
# Settings that pace requests and change no answer, so they stay out of the setup's version.
PACING = ("max_workers", "seconds_between_requests", "domains_per_call", "domains_per_request")
HARNESS = Path(__file__).resolve().parent
# Harness modules that schedule requests and change no answer.
NOT_ANSWER_CODE = ("run.py", "runner.py")
_GATES: dict[str, tuple[_Pacer, Any]] = {}
_GATES_LOCK = threading.Lock()


def answer(question: dict[str, Any], setup: str, *, dry: bool, tracer: Any = None) -> dict[str, Any]:
    """One setup's answer for one question row. `dry` returns a canned reply and sends nothing.

    The `answer` string is always the three graded fields as JSON, null where the setup gave no value.
    A vendor's 5xx, a refusal of our key or credits (401, 402, 403, 429), and a failure of ours raise, so obkit records an
    infra_error with the full hold and asks again; none of them is scored against the vendor.
    `tracer` is accepted for obkit's signature and not used.
    """
    company = Company(question["domain"], question.get("company") or None)
    if dry:
        return _canned(question, setup)
    try:
        found = _lookup(registry.build(setup), company)
    except HttpError as exc:
        return _failed(exc.response.status, str(exc))
    except http_client.HTTPError as exc:
        return _failed(exc.status, str(exc))
    except (ValueError, TimeoutError) as exc:  # the vendor's answer did not parse, or its run did not finish in time
        return _row("vendor_error", error=f"{type(exc).__name__}: {exc}")
    if found.status == "not_found":
        return _row("vendor_empty", error=found.error)
    if found.status == "error":
        return _failed(_status_code(found.error), found.error or "")
    status = "ok" if any(found.fields.get(f) is not None for f in FIELDS) else "vendor_empty"
    return _row(status, found.fields, cost_usd=float(found.cost_units or 0) if found.cost_unit == "usd" else 0.0)


def contract(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """What a setup sees first, per question. No network. The search-then-extract user message is shown with no results.
    Refuses a set holding a question whose ground truth names no stage: the board grades only the stage, so such a
    question would be a judge error on every setup."""
    unscored = [q["domain"] for q in questions if grade_stage(q.get("latest_stage"), "Series A") == "not_scoreable"]
    if unscored:
        raise ValueError(f"ground truth names no stage for {len(unscored)} questions, e.g. {unscored[:3]}; drop them")
    companies = [Company(q["domain"], q.get("company") or None) for q in questions]
    return {
        "output_schema": OUTPUT_SCHEMA,
        "extraction_system_prompt": SEARCH_EXTRACTION_PROMPT,
        "per_question": {c.domain: {"instruction": instruction(c), "extraction_user_content": user_content(c, [])}
                         for c in companies},
    }


def probe(setup: str) -> dict[str, Any]:
    """The first request `setup` sends for PROBE_COMPANY, recorded offline. Keys are replaced with placeholders."""
    adapter = registry.build(setup)
    sent: dict[str, Any] = {}

    class _Captured(Exception):
        pass

    def fake_request(method: str, url: str, **kwargs: Any) -> None:
        sent.update(method=method, url=url, **kwargs)
        raise _Captured

    def fake_run(args: Any, **_: Any) -> None:
        argv = list(args)
        if "--file" in argv:  # the CLI reads its payload from a temp file whose name is random
            with open(argv[argv.index("--file") + 1]) as handle:
                argv[argv.index("--file") + 1] = json.load(handle)
        sent.update(argv=argv)
        raise _Captured

    placeholders = {name: "probe-placeholder" for name in adapter.env}
    with mock.patch.dict(os.environ, placeholders), \
            mock.patch.object(http_client, "request", fake_request), \
            mock.patch.object(subprocess, "run", fake_run):
        try:
            adapter.lookup(PROBE_COMPANY)
        except Exception:
            if not sent:
                raise
    if not sent:
        raise RuntimeError(f"{setup} sent no request for the probe company")
    sent["settings"] = {k: v for k, v in adapter.settings.items() if k not in PACING}
    files = _answer_files(adapter)
    sent["code"] = _code_digest(files)
    sent["packages"] = _packages(files)
    return sent


def _answer_files(adapter: Any) -> list[Path]:
    """The code that turns a vendor's reply into this setup's answer: its adapter module and every harness module it
    imports, followed through their imports, plus this hook and the registry."""
    own = Path(sys.modules[type(adapter).__module__].__file__).resolve()
    return sorted(_imported(own) | {HARNESS / "obkit.py", HARNESS / "registry.py"})


def _code_digest(files: list[Path]) -> str:
    """sha256 of `files`, each as normalized source (docstrings dropped, `ast.unparse`), so comments, docstrings and
    layout do not count, and every Python version gives the same digest. A parsing change moves the digest and the
    setup answers again."""
    digest = hashlib.sha256()
    for path in files:
        digest.update(f"{path.relative_to(HARNESS).as_posix()}\n{_source(path)}\n".encode())
    return digest.hexdigest()


def _packages(files: list[Path]) -> dict[str, str]:
    """The installed version of every third-party package `files` import (an SDK or parsing library on the answer
    path), so a different version of one is a different setup version. Raises when the venv differs from a pin in
    requirements.txt or an import has no installed package, so a stale venv is refused instead of re-versioning setups."""
    _check_pins()
    names = {
        name.split(".")[0]
        for path in files for node in ast.walk(ast.parse(path.read_bytes()))
        for name in ([n.name for n in node.names] if isinstance(node, ast.Import)
                     else [node.module] if isinstance(node, ast.ImportFrom) and not node.level and node.module else [])
    } - set(sys.stdlib_module_names) - {"harness"}
    owners = importlib.metadata.packages_distributions()
    if missing := sorted(n for n in names if not owners.get(n)):
        raise RuntimeError(f"no installed package provides {', '.join(missing)}: run uv pip install -r requirements.txt")
    return {dist: importlib.metadata.version(dist) for name in sorted(names) for dist in owners[name]}


def _check_pins() -> None:
    installed = {_canon(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
    pins = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", (HARNESS.parent / "requirements.txt").read_text(), re.M)
    if wrong := [f"{name} {installed[_canon(name)]} (pinned {pin})" for name, pin in pins
                 if _canon(name) in installed and installed[_canon(name)] != pin]:
        raise RuntimeError(f"installed versions differ from requirements.txt: {', '.join(wrong)}: "
                           "run uv pip install -r requirements.txt")


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _imported(start: Path) -> set[Path]:
    """`start` and the harness modules it imports, directly or through other harness modules."""
    seen: set[Path] = set()
    todo = [start]
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        package = path.relative_to(HARNESS).parent.parts
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.ImportFrom) and node.level:
                base = [*package[:len(package) - node.level + 1], *(node.module.split(".") if node.module else [])]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "harness":
                base = node.module.split(".")[1:]
            elif isinstance(node, ast.Import):
                todo += _module_files([[*n.name.split(".")[1:]] for n in node.names if n.name.split(".")[0] == "harness"])
                continue
            else:
                continue
            todo += _module_files([base, *[[*base, alias.name] for alias in node.names]])
    return seen


def _module_files(names: list[list[str]]) -> list[Path]:
    files = []
    for parts in names:
        for path in (HARNESS.joinpath(*parts, "__init__.py"), HARNESS.joinpath(*parts[:-1], f"{parts[-1]}.py") if parts else None):
            if path is not None and path.is_file() and path.name not in NOT_ANSWER_CODE:
                files.append(path.resolve())
    return files


def _source(path: Path) -> str:
    tree = ast.parse(path.read_bytes())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _lookup(adapter: Any, company: Company) -> Any:
    """`adapter.lookup`, keeping the setup's `max_workers` and `seconds_between_requests` across obkit's threads."""
    with _GATES_LOCK:
        if adapter.setup not in _GATES:
            slots = threading.BoundedSemaphore(adapter.max_workers) if adapter.max_workers else contextlib.nullcontext()
            _GATES[adapter.setup] = (_Pacer(adapter.seconds_between_requests), slots)
        pacer, slots = _GATES[adapter.setup]
    with slots:
        pacer.wait()
        return adapter.lookup(company)


def _row(status: str, fields: dict[str, Any] | None = None, *, error: str | None = None, cost_usd: float = 0.0) -> dict[str, Any]:
    values = {f: (fields or {}).get(f) for f in FIELDS}
    return {"status": status, "answer": json.dumps(values), "error": error, "cost_usd": cost_usd}


def _failed(code: int | None, message: str) -> dict[str, Any]:
    """5xx is the vendor's outage, and 401, 402, 403 and 429 refuse our key, credits or rate: raise, so the row is
    infra_error. Other errors are the vendor's."""
    if code in (401, 402, 403, 429) or (code is not None and code >= 500):
        raise RuntimeError(message)
    return _row("vendor_error", error=message[:300])


def _status_code(error: str | None) -> int | None:
    """The status that leads an error, as in "HTTP 429: ..." (http_failure) or "HTTPError: HTTP 402 from ..."."""
    match = re.match(r"(?:\w+: )?HTTP (\d{3})\b", error or "")
    return int(match.group(1)) if match else None


def _canned(question: dict[str, Any], setup: str) -> dict[str, Any]:
    """A reply with no network: the question's truth, or the amount doubled, chosen by a hash of setup and domain."""
    truth = {f: question[f] for f in FIELDS}
    odd = hashlib.sha256(f"{setup}|{question['domain']}".encode()).digest()[0] % 2
    fields = dict(truth, amount=truth["amount"] * 2) if odd else truth
    return _row("ok", fields)
