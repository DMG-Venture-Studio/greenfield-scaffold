"""Declare every key the project uses, keep values out of the repository, and mint and age them in Infisical.

    uv run python tools/toolkit/credentials.py check
    uv run python tools/toolkit/credentials.py provision --env staging [--only NAME ...]
    uv run python tools/toolkit/credentials.py rotate NAME --env prod
    uv run python tools/toolkit/credentials.py adopt NAME --env prod [--minted YYYY-MM-DD]
    uv run python tools/toolkit/credentials.py probe NAME --env staging
    uv run python tools/toolkit/credentials.py audit [--json report.json]

`check` needs no network: the manifest agrees with the spec's adapters, and no file git would commit holds
something shaped like a vendor key. The rest talk to Infisical as the signed-in person (`infisical login`) or
as a machine identity (`INFISICAL_TOKEN`). A person mints each key in the vendor's dashboard and copies it;
the script reads the clipboard, checks the key against the vendor, stores it, and clears the clipboard. A
value is never printed, logged, put in argv or written to disk, so an agent driving the script never sees
one. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import shlex
import ssl
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

type Json = dict[str, object]

MANIFEST, SPEC = "credentials.toml", "project-spec.toml"
UPPER = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$")
SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
FOLDER = re.compile(r"^/([a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*)?$")
LOCAL_HOSTS = ("localhost", "127.0.0.1")
SUCCESS = range(200, 300)
NOT_FOUND = 404
DUE_SOON_DAYS = 14
FINGERPRINT_CHARS = 12
TAIL_CHARS = 4
MAX_SCAN_BYTES = 1_000_000
TIMEOUT_SECONDS = 20
AGENT = "greenfield-credentials"
# Points every vendor probe at one server instead of the vendors: for tests, or an egress proxy.
VENDOR_BASE = "CREDENTIALS_VENDOR_BASE"
PASTE, CLEAR = "CREDENTIALS_PASTE", "CREDENTIALS_CLEAR"


@dataclass(frozen=True)
class Probe:
    """One cheap authenticated call that succeeds only with a working key."""

    method: str
    url: str
    header: str
    bearer: bool = True
    body: str = ""
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Vendor:
    """Where a vendor's keys are minted and revoked, what one looks like, and how to test one."""

    label: str
    sdks: tuple[str, ...]
    keys_page: str
    shape: str
    leak: str
    probe: Probe | None
    expires: bool
    note: str


VENDORS: dict[str, Vendor] = {
    "anthropic": Vendor(
        "Anthropic",
        ("anthropic",),
        "https://platform.claude.com/settings/keys",
        r"sk-ant-api\d{2}-[A-Za-z0-9_-]{80,}",
        r"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{80,}",
        Probe(
            "GET",
            "https://api.anthropic.com/v1/models",
            "x-api-key",
            bearer=False,
            extra=(("anthropic-version", "2023-06-01"),),
        ),
        expires=True,
        note="Mint it in this project's workspace for this environment, which carries the spend cap.",
    ),
    "replicate": Vendor(
        "Replicate",
        ("replicate",),
        "https://replicate.com/account/api-tokens",
        r"r8_[A-Za-z0-9]{30,}",
        r"\br8_[A-Za-z0-9]{37}\b",
        Probe("GET", "https://api.replicate.com/v1/account", "Authorization"),
        expires=False,
        note="Name the token after this project and environment, so it can be found to revoke.",
    ),
    "workos": Vendor(
        "WorkOS",
        ("workos",),
        "https://dashboard.workos.com/",
        r"sk_[A-Za-z0-9_]{20,}",
        r"\bsk_(?:test|live)_[A-Za-z0-9]{24,}",
        Probe("GET", "https://api.workos.com/organizations?limit=1", "Authorization"),
        expires=True,
        note="Switch to the WorkOS environment first, then API Keys: a key acts only in its environment.",
    ),
    "openai": Vendor(
        "OpenAI",
        ("openai",),
        "https://platform.openai.com/api-keys",
        r"sk-(?!ant-)[A-Za-z0-9_-]{40,}",
        r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{40,}",
        Probe("GET", "https://api.openai.com/v1/models", "Authorization"),
        expires=False,
        note="Mint it in the OpenAI project for this environment, which carries the budget.",
    ),
    "stripe": Vendor(
        "Stripe",
        ("stripe",),
        "https://dashboard.stripe.com/apikeys",
        r"[rs]k_(?:test|live)_[A-Za-z0-9]{24,}",
        r"\b[rs]k_(?:test|live)_[A-Za-z0-9]{24,}",
        Probe("GET", "https://api.stripe.com/v1/balance", "Authorization"),
        expires=False,
        note="Prefer a restricted key (rk_) limited to what the adapter calls.",
    ),
    "github": Vendor(
        "GitHub",
        ("github",),
        "https://github.com/settings/personal-access-tokens",
        r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,})",
        Probe(
            "GET",
            "https://api.github.com/user",
            "Authorization",
            extra=(("Accept", "application/vnd.github+json"),),
        ),
        expires=True,
        note="A fine-grained token limited to the repositories and permissions the row's purpose names.",
    ),
    "railway": Vendor(
        "Railway",
        (),
        "https://railway.com/dashboard",
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "",
        Probe(
            "POST",
            "https://backboard.railway.com/graphql/v2",
            "Project-Access-Token",
            bearer=False,
            body='{"query": "{ projectToken { projectId environmentId } }"}',
        ),
        expires=False,
        note="Project settings, Tokens, for one environment: it controls that environment, not just reads.",
    ),
    "other": Vendor("another vendor", (), "", "", "", None, expires=False, note="See the row's purpose."),
}
SDK_VENDOR = {sdk: key for key, vendor in VENDORS.items() for sdk in vendor.sdks}
LEAKS = [(key, re.compile(vendor.leak)) for key, vendor in VENDORS.items() if vendor.leak]


@dataclass(frozen=True)
class Credential:
    """One key the project uses, in the folder and the environments the manifest gives it."""

    name: str
    vendor: str
    path: str
    envs: tuple[str, ...]
    adapter: str = ""
    purpose: str = ""
    keys_page: str = ""
    rotate_days: dict[str, int] = field(default_factory=dict)

    def at(self, env: str) -> str:
        """Where the value lives in Infisical, for messages: environment and folder."""
        return f"{env}:{self.path}"


@dataclass(frozen=True)
class Manifest:
    """The parsed `credentials.toml`."""

    host: str
    project_id: str
    environments: tuple[str, ...]
    rotate_days: dict[str, int]
    credentials: tuple[Credential, ...]

    def window(self, cred: Credential, env: str) -> int:
        """Days a key may live in one environment before rotation; 0 means rotate on events only."""
        return cred.rotate_days.get(env, self.rotate_days.get(env, 0))


def _table(value: object) -> Json:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def _rows(value: object) -> list[Json]:
    return [_table(v) for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _strs(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _str(table: Json, key: str) -> str:
    value = table.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _days(value: object) -> dict[str, int]:
    table = _table(value)
    return {k: v for k, v in table.items() if isinstance(v, int) and not isinstance(v, bool)}


# The manifest's rules. The engine refuses an intake with these same rules, so a scaffold never ships a
# manifest that its own check fails.


def _host_problems(host: str) -> list[str]:
    if not host:
        return []
    parts = urlsplit(host)
    if (parts.scheme == "https" and parts.hostname) or (
        parts.scheme == "http" and parts.hostname in LOCAL_HOSTS
    ):
        return []
    return [f"manager: host {host!r} must be an https URL (plain http only for localhost)"]


def _days_problems(where: str, raw: object, envs: list[str]) -> list[str]:
    table = _table(raw)
    out = [f"{where}: rotate_days names unknown environment {e!r}" for e in table if e not in envs]
    out += [
        f"{where}: rotate_days for {e} must be a whole number of days, 0 for rotate on events only"
        for e, v in table.items()
        if not isinstance(v, int) or isinstance(v, bool) or v < 0
    ]
    return out


def _manager_problems(manager: Json) -> list[str]:
    envs = _strs(manager.get("environments"))
    out = [] if _str(manager, "kind") == "infisical" else ['manager: kind must be "infisical"']
    out += _host_problems(_str(manager, "host"))
    if not envs:
        out.append("manager: declare at least one environment")
    out += [f"manager: environment {e!r} is not a lowercase slug" for e in envs if not SLUG.match(e)]
    out += [f"manager: environment {e!r} is declared twice" for e in set(envs) if envs.count(e) > 1]
    return out + _days_problems("manager", manager.get("rotate_days"), envs)


def _row_problems(row: Json, envs: list[str], adapters: dict[str, str]) -> list[str]:
    name, vendor, adapter = _str(row, "name"), _str(row, "vendor"), _str(row, "adapter")
    where = f"credential {name or '?'}"
    out = [] if UPPER.match(name) else [f"{where}: name must be UPPER_SNAKE, the variable the code reads"]
    if vendor not in VENDORS:
        out.append(f"{where}: vendor {vendor!r} is not one of {sorted(VENDORS)}")
    row_envs = _strs(row.get("envs")) or envs
    out += [f"{where}: environment {e!r} is not declared under [manager]" for e in row_envs if e not in envs]
    if not FOLDER.match(_str(row, "path") or "/"):
        out.append(f"{where}: path must be / or a folder like /worker (lowercase, hyphens)")
    if adapter and adapter not in adapters:
        out.append(f"{where}: names adapter {adapter!r}, which the spec does not declare")
    sdk_vendor = SDK_VENDOR.get(adapters.get(adapter, ""), "")
    if sdk_vendor and vendor in VENDORS and vendor != sdk_vendor:
        out.append(f"{where}: adapter {adapter} wraps {adapters[adapter]}, so its vendor is {sdk_vendor}")
    page = _str(row, "keys_page")
    if vendor == "other" and not page.startswith("https://"):
        out.append(f"{where}: vendor other needs keys_page, the https page where its keys are minted")
    return out + _days_problems(where, row.get("rotate_days"), row_envs)


def manifest_problems(data: Json, adapters: dict[str, str]) -> list[str]:
    """Every way the manifest disagrees with itself or with the spec's adapters (name to import name)."""
    manager = _table(data.get("manager"))
    envs = _strs(manager.get("environments"))
    rows = _rows(data.get("credentials"))
    out = _manager_problems(manager)
    for row in rows:
        out += _row_problems(row, envs, adapters)
    keys = [(_str(r, "name"), _str(r, "path") or "/") for r in rows]
    out += [
        f"credential {n} in {p} is declared twice" for n, p in sorted(set(keys)) if keys.count((n, p)) > 1
    ]
    named = {_str(r, "adapter") for r in rows}
    out += [
        f"adapter {a} wraps {w}, a vendor SDK, but no credential names it"
        for a, w in sorted(adapters.items())
        if w in SDK_VENDOR and a not in named
    ]
    return out


def manifest(data: Json) -> Manifest:
    """The manifest as records; call `manifest_problems` first."""
    manager = _table(data.get("manager"))
    envs = tuple(_strs(manager.get("environments")))
    creds = tuple(
        Credential(
            name=_str(r, "name"),
            vendor=_str(r, "vendor"),
            path=_str(r, "path") or "/",
            envs=tuple(_strs(r.get("envs"))) or envs,
            adapter=_str(r, "adapter"),
            purpose=_str(r, "purpose"),
            keys_page=_str(r, "keys_page"),
            rotate_days=_days(r.get("rotate_days")),
        )
        for r in _rows(data.get("credentials"))
    )
    return Manifest(
        _str(manager, "host").rstrip("/"),
        _str(manager, "project_id"),
        envs,
        _days(manager.get("rotate_days")),
        creds,
    )


# The leak scan: what git would commit, read as text, searched for anything shaped like a vendor key.


def _candidates(root: Path) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if listed.returncode:
        skip = {".git", ".venv", "node_modules", "__pycache__"}
        return sorted(p for p in root.rglob("*") if p.is_file() and not skip & set(p.relative_to(root).parts))
    names = {n for n in listed.stdout.decode().split("\0") if n}
    return sorted(root / n for n in names if (root / n).is_file())


def _text(path: Path) -> str | None:
    if path.stat().st_size > MAX_SCAN_BYTES:
        return None
    raw = path.read_bytes()
    return None if b"\0" in raw else raw.decode("utf-8", errors="replace")


def _line_leak(line: str) -> str | None:
    return next((VENDORS[key].label for key, pattern in LEAKS if pattern.search(line)), None)


def leaks(root: Path) -> list[str]:
    """Each line, in a file git would commit, that holds something shaped like a vendor key."""
    out = []
    for path in _candidates(root):
        text = _text(path)
        for number, line in enumerate((text or "").splitlines(), 1):
            label = _line_leak(line)
            if label:
                out.append(
                    f"{path.relative_to(root)}:{number}: looks like a key for {label}; move it to the "
                    "secrets manager and revoke it, since it has been on disk"
                )
    return out


# HTTP, for Infisical and the vendor probes. A credential never goes over plain http except to localhost.


def _http(method: str, url: str, headers: dict[str, str], body: str = "") -> tuple[int, Json]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" and host not in LOCAL_HOSTS:
        raise SystemExit(f"refusing to send a credential over plain http to {host}")
    if parts.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, parts.port, timeout=TIMEOUT_SECONDS
        )
    else:
        connection = http.client.HTTPConnection(host, parts.port, timeout=TIMEOUT_SECONDS)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    sent = {"User-Agent": AGENT, **headers} | ({"Content-Type": "application/json"} if body else {})
    try:
        connection.request(method, target, body=body.encode() if body else None, headers=sent)
        response = connection.getresponse()
        status, raw = response.status, response.read()
    except ssl.SSLCertVerificationError as error:
        raise SystemExit(f"{host}: {error}; point SSL_CERT_FILE at a CA bundle and retry") from error
    except OSError as error:
        raise SystemExit(f"cannot reach {host}: {error}") from error
    finally:
        connection.close()
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = {}
    return status, _table(data)


def _probe_url(url: str) -> str:
    base = os.environ.get(VENDOR_BASE, "")
    if not base:
        return url
    over, parts = urlsplit(base), urlsplit(url)
    return urlunsplit((over.scheme, over.netloc, parts.path, parts.query, ""))


def probe(vendor: str, value: str) -> tuple[bool, str]:
    """Call the vendor with the key: whether it worked, and what the answer said that is safe to show."""
    spec = VENDORS[vendor].probe
    if spec is None:
        return True, "no probe for this vendor"
    headers = {spec.header: f"Bearer {value}" if spec.bearer else value, **dict(spec.extra)}
    status, data = _http(spec.method, _probe_url(spec.url), headers, spec.body)
    if status not in SUCCESS or data.get("errors"):
        return False, f"{VENDORS[vendor].label} answered {status}"
    found = _table(_table(data.get("data")).get("projectToken"))
    if found:
        return True, f"project {_str(found, 'projectId')}, environment {_str(found, 'environmentId')}"
    return True, f"{VENDORS[vendor].label} answered {status}"


def fingerprint(value: str) -> str:
    """A short hash that tells two values apart without revealing either."""
    return hashlib.sha256(value.encode()).hexdigest()[:FINGERPRINT_CHARS]


@dataclass(frozen=True)
class Infisical:
    """Infisical's HTTP API for one project, as whoever signed in."""

    host: str
    project_id: str
    bearer: str

    def call(
        self, method: str, path: str, *, query: dict[str, str] | None = None, body: Json | None = None
    ) -> Json:
        """One request; a failure stops the script with Infisical's own message."""
        url = self.host + path + (f"?{urlencode(query)}" if query else "")
        status, data = _http(
            method, url, {"Authorization": f"Bearer {self.bearer}"}, json.dumps(body) if body else ""
        )
        if status == NOT_FOUND and method == "GET" and path.startswith("/api/v4/secrets/"):
            return {}
        if status not in SUCCESS:
            raise SystemExit(
                f"Infisical refused {method} {path} ({status}): {_str(data, 'message') or 'no message'}"
            )
        return data

    def stored(self, cred: Credential, env: str, *, value: bool = False) -> Json:
        """The secret's record in one environment, or {} when it is not there; its value only when asked."""
        query = {
            "projectId": self.project_id,
            "environment": env,
            "secretPath": cred.path,
            "viewSecretValue": "true" if value else "false",
            "expandSecretReferences": "false",
            "includeImports": "false",
        }
        return _table(self.call("GET", f"/api/v4/secrets/{quote(cred.name)}", query=query).get("secret"))

    def ensure_folder(self, env: str, path: str) -> None:
        """Create each folder on the path that does not exist yet."""
        parent = "/"
        for name in [part for part in path.split("/") if part]:
            query = {"projectId": self.project_id, "environment": env, "path": parent}
            names = {
                _str(f, "name")
                for f in _rows(self.call("GET", "/api/v2/folders", query=query).get("folders"))
            }
            if name not in names:
                body: Json = {"projectId": self.project_id, "environment": env, "name": name, "path": parent}
                self.call("POST", "/api/v2/folders", body=body)
            parent = f"{parent.rstrip('/')}/{name}"


def _today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


def store(api: Infisical, cred: Credential, env: str, value: str, *, existing: bool, days: int) -> None:
    """Write the value with its mint date and fingerprint, and a rotation reminder on a new secret."""
    meta = [
        {"key": "minted_at", "value": _today()},
        {"key": "vendor", "value": cred.vendor},
        {"key": "fingerprint", "value": fingerprint(value)},
    ]
    body: Json = {
        "projectId": api.project_id,
        "environment": env,
        "secretPath": cred.path,
        "secretValue": value,
        "secretComment": f"{cred.purpose} Minted {_today()} with tools/toolkit/credentials.py.".strip(),
        "secretMetadata": meta,
    }
    if not existing:
        api.ensure_folder(env, cred.path)
        if days:
            body["secretReminderRepeatDays"] = days
            body["secretReminderNote"] = (
                f"uv run python tools/toolkit/credentials.py rotate {cred.name} --env {env}"
            )
    answer = api.call("PATCH" if existing else "POST", f"/api/v4/secrets/{quote(cred.name)}", body=body)
    if "approval" in answer:
        print(f"  Infisical holds the change to {cred.name} in {env} for approval before it applies")


# The person's side: the clipboard and the vendor's page.


def _command(variable: str, default: str) -> list[str]:
    return shlex.split(os.environ.get(variable, default))


def _paste() -> str:
    try:
        done = subprocess.run(_command(PASTE, "pbpaste"), capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise SystemExit(f"cannot read the clipboard; set {PASTE} to a command that prints it") from error
    return done.stdout.strip()


def _clear() -> None:
    try:
        subprocess.run(_command(CLEAR, "pbcopy"), input="", capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print(f"  could not clear the clipboard; set {CLEAR}, and clear it by hand now")


def _shape_problem(vendor: Vendor, value: str) -> str | None:
    if not value:
        return "the clipboard is empty"
    if any(c.isspace() for c in value):
        return "the clipboard holds more than one word"
    if vendor.shape and not re.fullmatch(vendor.shape, value):
        return f"the clipboard holds {len(value)} characters that do not look like a key for {vendor.label}"
    return None


def mint(cred: Credential, env: str, *, days: int, open_page: bool) -> str:
    """Send the person to the vendor's page, and read the key they copy from the clipboard."""
    vendor = VENDORS[cred.vendor]
    page = cred.keys_page or vendor.keys_page
    expiry = f" Give it an expiry of {days} days." if vendor.expires and days else ""
    print(f"\n{cred.name} for {cred.at(env)}: mint it at {page}\n  {vendor.note}{expiry}")
    if cred.purpose:
        print(f"  It is for: {cred.purpose}")
    if open_page:
        subprocess.run(["open", page], capture_output=True, check=False)
    input("  Copy the new key, then press Enter. It is read from the clipboard and never shown. ")
    value = _paste()
    problem = _shape_problem(vendor, value)
    if problem:
        raise SystemExit(f"{cred.name}: {problem}; nothing was stored")
    return value


def _verify(cred: Credential, value: str, *, check_key: bool) -> str:
    if not check_key:
        return "not probed"
    worked, detail = probe(cred.vendor, value)
    if not worked:
        _clear()
        raise SystemExit(f"{cred.name}: the key did not work ({detail}); nothing was stored")
    return detail


# The commands.


def _read(root: Path, name: str) -> Json:
    path = root / name
    return tomllib.loads(path.read_text()) if path.is_file() else {}


def _spec_adapters(root: Path) -> dict[str, str]:
    return {_str(a, "name"): _str(a, "wraps") for a in _rows(_read(root, SPEC).get("adapters"))}


def _load(root: Path) -> Manifest:
    if not (root / MANIFEST).is_file():
        raise SystemExit(
            f"{MANIFEST} is missing; the scaffold writes it when the project declares credentials"
        )
    data = _read(root, MANIFEST)
    problems = manifest_problems(data, _spec_adapters(root))
    if problems:
        raise SystemExit(f"{MANIFEST} has problems; run check:\n" + "\n".join(f"- {p}" for p in problems))
    return manifest(data)


def _bearer(host: str) -> str:
    from_env = os.environ.get("INFISICAL_TOKEN", "").strip()
    if from_env:
        return from_env
    try:
        done = subprocess.run(
            ["infisical", "user", "get", "token", "--plain"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        done = None
    lines = done.stdout.strip().splitlines() if done and not done.returncode else []
    if not lines:
        raise SystemExit(
            f"sign in first (`infisical login --domain {host}`), or set INFISICAL_TOKEN for a machine"
        )
    return lines[-1].strip()


def _session(root: Path) -> tuple[Manifest, Infisical]:
    found = _load(root)
    if not found.host or not found.project_id:
        raise SystemExit(
            f"{MANIFEST}: set [manager] host and project_id (the Infisical URL, and the project's ID "
            "from its settings page) before this command can reach Infisical"
        )
    return found, Infisical(found.host, found.project_id, _bearer(found.host))


def _one(found: Manifest, name: str, env: str, path: str | None) -> Credential:
    rows = [c for c in found.credentials if c.name == name and (path is None or c.path == path)]
    if len(rows) != 1:
        where = "several folders; pass --path" if rows else f"no row in {MANIFEST}"
        raise SystemExit(f"{name}: {where}")
    if env not in rows[0].envs:
        raise SystemExit(f"{name}: {MANIFEST} does not declare it in {env}")
    return rows[0]


def check(root: Path) -> int:
    """The manifest agrees with the spec, and nothing git would commit looks like a vendor key."""
    data = _read(root, MANIFEST) if (root / MANIFEST).is_file() else None
    problems = [f"{MANIFEST} is missing"] if data is None else manifest_problems(data, _spec_adapters(root))
    problems += leaks(root)
    if problems:
        sys.stderr.write("".join(f"{p}\n" for p in problems))
        return 1
    count = len(_rows((data or {}).get("credentials")))
    print(f"credentials: {count} declared, every vendor adapter covered, no key in the tree")
    return 0


def provision(root: Path, env: str, only: list[str], *, open_page: bool, check_key: bool) -> int:
    """Mint and store every credential the environment lacks; leave the ones already there alone."""
    found, api = _session(root)
    if env not in found.environments:
        raise SystemExit(f"{env} is not an environment in {MANIFEST}: {', '.join(found.environments)}")
    for cred in [c for c in found.credentials if env in c.envs and (not only or c.name in only)]:
        if api.stored(cred, env):
            print(f"present  {cred.name} in {cred.at(env)}")
            continue
        days = found.window(cred, env)
        value = mint(cred, env, days=days, open_page=open_page)
        detail = _verify(cred, value, check_key=check_key)
        store(api, cred, env, value, existing=False, days=days)
        _clear()
        print(f"stored   {cred.name} in {cred.at(env)}: {detail}; fingerprint {fingerprint(value)}")
    return 0


def rotate(root: Path, name: str, env: str, path: str | None, *, open_page: bool, check_key: bool) -> int:
    """Replace one stored key with a newly minted one; Infisical keeps the old version for rollback."""
    found, api = _session(root)
    cred = _one(found, name, env, path)
    old = api.stored(cred, env, value=True)
    if not old:
        raise SystemExit(f"{name} is not stored in {cred.at(env)}; run provision --env {env}")
    old_value = "" if old.get("secretValueHidden") else _str(old, "secretValue")
    value = mint(cred, env, days=found.window(cred, env), open_page=open_page)
    if value == old_value:
        raise SystemExit(f"{name}: the clipboard still holds the key in use; copy the new one")
    detail = _verify(cred, value, check_key=check_key)
    store(api, cred, env, value, existing=True, days=0)
    _clear()
    was = fingerprint(old_value) if old_value else "hidden"
    print(f"rotated  {name} in {cred.at(env)}: {detail}; fingerprint {was} -> {fingerprint(value)}")
    print(f"  Infisical keeps version {old.get('version', '?')} for rollback.")
    tail = f", the one ending ...{old_value[-TAIL_CHARS:]}" if old_value else ""
    page = cred.keys_page or VENDORS[cred.vendor].keys_page
    print(f"  Revoke the old key at {page}{tail}, once every service has picked up the new one.")
    return 0


def adopt(root: Path, name: str, env: str, path: str | None, *, minted: str) -> int:
    """Record when an existing value was minted, for a key stored before this tool (an import, say)."""
    found, api = _session(root)
    cred = _one(found, name, env, path)
    old = api.stored(cred, env, value=True)
    if not old:
        raise SystemExit(f"{name} is not stored in {cred.at(env)}; run provision --env {env}")
    dt.date.fromisoformat(minted)
    meta = [{"key": "minted_at", "value": minted}, {"key": "vendor", "value": cred.vendor}]
    if not old.get("secretValueHidden"):
        meta.append({"key": "fingerprint", "value": fingerprint(_str(old, "secretValue"))})
    body: Json = {
        "projectId": api.project_id,
        "environment": env,
        "secretPath": cred.path,
        "secretMetadata": meta,
    }
    api.call("PATCH", f"/api/v4/secrets/{quote(cred.name)}", body=body)
    print(f"adopted  {name} in {cred.at(env)}: minted {minted}")
    return 0


def check_stored(root: Path, name: str, env: str, path: str | None) -> int:
    """Call the vendor with the stored key, to see that it still works."""
    found, api = _session(root)
    cred = _one(found, name, env, path)
    stored = api.stored(cred, env, value=True)
    if not stored:
        raise SystemExit(f"{name} is not stored in {cred.at(env)}")
    worked, detail = probe(cred.vendor, _str(stored, "secretValue"))
    print(f"{'works' if worked else 'FAILS'}    {name} in {cred.at(env)}: {detail}")
    return 0 if worked else 1


def _minted(record: Json) -> dt.date | None:
    meta = {_str(m, "key"): _str(m, "value") for m in _rows(record.get("secretMetadata"))}
    try:
        return dt.date.fromisoformat(meta.get("minted_at", ""))
    except ValueError:
        return None


def _age(api: Infisical, found: Manifest, cred: Credential, env: str) -> Json:
    record, window = api.stored(cred, env), found.window(cred, env)
    row: Json = {"name": cred.name, "env": env, "path": cred.path, "window_days": window}
    minted = _minted(record) if record else None
    age = (dt.datetime.now(dt.UTC).date() - minted).days if minted else None
    if not record:
        status = "missing"
    elif age is None:
        status = "unknown age"
    elif window and age > window:
        status = "overdue"
    elif window and age > window - DUE_SOON_DAYS:
        status = "due soon"
    else:
        status = "ok"
    return row | {"status": status, "age_days": age}


def audit(root: Path, json_out: Path | None) -> int:
    """Every declared credential in each of its environments: present, and inside its rotation window."""
    found, api = _session(root)
    rows = [_age(api, found, cred, env) for cred in found.credentials for env in cred.envs]
    for row in rows:
        age = "-" if row["age_days"] is None else f"{row['age_days']}d"
        window = f"/{row['window_days']}d" if row["window_days"] else " (events)"
        print(f"{row['status']:<12} {row['name']} in {row['env']}:{row['path']}  {age}{window}")
    if json_out:
        json_out.write_text(json.dumps({"generated": _today(), "credentials": rows}, indent=1) + "\n")
    failing = [r for r in rows if r["status"] in {"missing", "overdue"}]
    return 1 if failing else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--root", type=Path, default=Path(), help="the repository root (default: here)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="the manifest agrees with the spec; no key in the tree")
    prov = sub.add_parser("provision", help="mint and store every key an environment lacks")
    prov.add_argument("--env", required=True)
    prov.add_argument("--only", nargs="*", default=[])
    for name in ("rotate", "adopt", "probe"):
        one = sub.add_parser(name)
        one.add_argument("name")
        one.add_argument("--env", required=True)
        one.add_argument("--path", default=None)
        if name == "adopt":
            one.add_argument("--minted", default=_today(), help="when the value was minted, YYYY-MM-DD")
    for each in (prov, sub.choices["rotate"]):
        each.add_argument("--no-open", action="store_true", help="do not open the vendor's page")
        each.add_argument("--no-probe", action="store_true", help="store without calling the vendor first")
    report = sub.add_parser("audit", help="every key present and inside its rotation window")
    report.add_argument("--json", type=Path, default=None)
    return parser


def main(argv: list[str]) -> int:
    """Run one command against the repository root."""
    args = _parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "check":
        return check(root)
    if args.command == "audit":
        return audit(root, args.json)
    if args.command == "adopt":
        return adopt(root, args.name, args.env, args.path, minted=args.minted)
    if args.command == "probe":
        return check_stored(root, args.name, args.env, args.path)
    flags = {"open_page": not args.no_open, "check_key": not args.no_probe}
    if args.command == "provision":
        return provision(root, args.env, args.only, **flags)
    return rotate(root, args.name, args.env, args.path, **flags)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
