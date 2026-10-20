"""credentials.py against a fake Infisical, fake vendors and a fake clipboard, with no network.

Proves: check refuses each manifest mistake and a key-shaped line in the tree; provision probes each key before
storing it, creates the folders, records the mint date and fingerprint, sets the reminder, clears the clipboard
and never prints a value; a key that fails its probe or is misshapen stores nothing; present keys are left
alone; rotate patches, names the old key's tail and refuses the key in use; audit fails on missing and overdue
keys; and a key is never sent over plain http to anything but localhost.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SCRIPT = Path(__file__).resolve().parents[2] / "plugins" / "greenfield" / "engine" / "toolkit" / "credentials.py"
BEARER = "test-bearer"
# Built by concatenation so no key-shaped literal sits in this repository for a scanner to trip on.
GOOD = "sk-ant-" + "api03-" + "g" * 90 + "AA"
GOOD_2 = "sk-ant-" + "api03-" + "h" * 90 + "BB"
WRONG = "sk-ant-" + "api03-" + "w" * 90 + "CC"
RAILWAY = "0b6c6f3e-1d2a-4c5b-9e8f-7a6b5c4d3e2f"
CREATE_KEYS = {
    "projectId",
    "environment",
    "secretPath",
    "secretValue",
    "secretComment",
    "secretMetadata",
    "secretReminderRepeatDays",
    "secretReminderNote",
    "type",
    "tagIds",
    "skipMultilineEncoding",
}
UPDATE_KEYS = {"projectId", "environment", "secretPath", "secretValue", "secretComment", "secretMetadata", "type"}

SPEC = """
[[adapters]]
name = "drafting"
wraps = "anthropic"
implements = "Drafter"
purpose = "Drafts."
"""

MANIFEST = """
[manager]
kind = "infisical"
host = "{host}"
project_id = "proj-1"
environments = ["dev", "staging", "prod"]
rotate_days = {{ dev = 90, staging = 90, prod = 0 }}

[[credentials]]
name = "ANTHROPIC_API_KEY"
vendor = "anthropic"
adapter = "drafting"
path = "/worker"
envs = ["staging", "prod"]
purpose = "The drafting adapter's calls to Claude."

[[credentials]]
name = "RAILWAY_STAGING_TOKEN"
vendor = "railway"
path = "/ops"
envs = ["staging"]
purpose = "The promote command's only credential."
"""


class Fake:
    """The state behind the fake server: secrets, folders, and every request it saw."""

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str, str], dict] = {}
        self.folders: set[tuple[str, str]] = {(e, "/") for e in ("dev", "staging", "prod")}
        self.log: list[tuple[str, str, dict]] = []


def handler(fake: Fake) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def reply(self, status: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def body(self) -> dict:
            size = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(size) or b"{}")

        def do_GET(self) -> None:
            self.route("GET", {})

        def do_POST(self) -> None:
            self.route("POST", self.body())

        def do_PATCH(self) -> None:
            self.route("PATCH", self.body())

        def route(self, method: str, body: dict) -> None:
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            fake.log.append((method, parts.path, body))
            if parts.path in {"/v1/models", "/graphql/v2"}:
                return self.vendor(parts.path)
            if self.headers.get("Authorization") != f"Bearer {BEARER}":
                return self.reply(401, {"message": "bad token"})
            if parts.path == "/api/v2/folders":
                return self.folders(method, query, body)
            return self.secret(method, unquote(parts.path.removeprefix("/api/v4/secrets/")), query, body)

        def vendor(self, path: str) -> None:
            if path == "/v1/models":
                ok = self.headers.get("x-api-key") in {GOOD, GOOD_2}
                return self.reply(200 if ok else 401, {"data": []} if ok else {"error": "invalid x-api-key"})
            if self.headers.get("Project-Access-Token") == RAILWAY:
                return self.reply(200, {"data": {"projectToken": {"projectId": "p1", "environmentId": "env-stg"}}})
            return self.reply(200, {"errors": [{"message": "Not Authorized"}]})

        def folders(self, method: str, query: dict, body: dict) -> None:
            if method == "GET":
                env, parent = query["environment"], query["path"].rstrip("/")
                names = [p.rsplit("/", 1)[1] for e, p in fake.folders if e == env and p.rsplit("/", 1)[0] == parent]
                return self.reply(200, {"folders": [{"name": n} for n in names if n]})
            fake.folders.add((body["environment"], f"{body['path'].rstrip('/')}/{body['name']}"))
            return self.reply(200, {"folder": {"name": body["name"]}})

        def secret(self, method: str, name: str, query: dict, body: dict) -> None:
            source = query if method == "GET" else body
            key = (source["environment"], source.get("secretPath", "/"), name)
            record = fake.secrets.get(key)
            if method == "GET":
                if record is None:
                    return self.reply(404, {"message": "Secret not found"})
                shown = dict(record)
                if query.get("viewSecretValue") == "false":
                    shown |= {"secretValue": "<hidden>", "secretValueHidden": True}
                return self.reply(200, {"secret": shown})
            allowed = CREATE_KEYS if method == "POST" else UPDATE_KEYS
            if set(body) - allowed:
                return self.reply(400, {"message": f"unknown properties {sorted(set(body) - allowed)}"})
            if method == "POST":
                if (key[0], key[1]) not in fake.folders:
                    return self.reply(404, {"message": "Folder not found"})
                fake.secrets[key] = {"secretKey": name, "version": 1, **body}
            else:
                fake.secrets[key] = {**record, **body, "version": record["version"] + 1}
            return self.reply(200, {"secret": {"secretKey": name, "version": fake.secrets[key]["version"]}})

    return Handler


class Rig:
    """A project folder, the fake server, and a clipboard that hands out one queued value per paste."""

    def __init__(self) -> None:
        self.fake = Fake()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.fake))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.root = Path(tempfile.mkdtemp())
        (self.root / "project-spec.toml").write_text(SPEC)
        (self.root / "credentials.toml").write_text(MANIFEST.format(host=self.url))
        self.queue = self.root.parent / f"{self.root.name}-clipboard.json"
        self.cleared = self.root.parent / f"{self.root.name}-cleared.log"
        pop = self.root.parent / f"{self.root.name}-pop.py"
        pop.write_text(
            "import json, sys\nq = json.loads(open(sys.argv[1]).read())\nprint(q.pop(0) if q else '')\n"
            "open(sys.argv[1], 'w').write(json.dumps(q))\n"
        )
        self.env = dict(
            os.environ,
            INFISICAL_TOKEN=BEARER,
            CREDENTIALS_VENDOR_BASE=self.url,
            CREDENTIALS_PASTE=f"{sys.executable} {pop} {self.queue}",
            CREDENTIALS_CLEAR=f"sh -c 'echo cleared >> {self.cleared}'",
        )
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def clipboard(self, *values: str) -> None:
        self.queue.write_text(json.dumps(list(values)))

    def run(self, *args: str, enters: int = 0, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), *args],
            input="\n" * enters,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        for value in (GOOD, GOOD_2, WRONG, RAILWAY):
            assert value not in done.stdout + done.stderr, f"a value was printed by {args}"
        return done

    def writes(self) -> list[tuple[str, str, dict]]:
        return [entry for entry in self.fake.log if entry[0] in {"POST", "PATCH"} and "secrets" in entry[1]]


def test_check_refuses_each_mistake_and_a_key_in_the_tree():
    rig = Rig()
    assert rig.run("check").returncode == 0
    manifest = rig.root / "credentials.toml"
    clean = manifest.read_text()
    cases = {
        'name = "GHOST"\nvendor = "replicate"\nadapter = "ghost"\n': "names adapter 'ghost'",
        'name = "ANTHROPIC_API_KEY"\nvendor = "anthropic"\nadapter = "drafting"\npath = "/worker"\n': "declared twice",
        'name = "lower"\nvendor = "replicate"\n': "UPPER_SNAKE",
        'name = "X_KEY"\nvendor = "acme"\n': "vendor 'acme'",
        'name = "X_KEY"\nvendor = "replicate"\nenvs = ["qa"]\n': "'qa' is not declared",
        'name = "X_KEY"\nvendor = "replicate"\nadapter = "drafting"\n': "its vendor is anthropic",
        'name = "X_KEY"\nvendor = "other"\n': "needs keys_page",
    }
    for row, says in cases.items():
        manifest.write_text(clean + "\n[[credentials]]\n" + row)
        done = rig.run("check")
        assert done.returncode == 1 and says in done.stderr, (says, done.stderr)
    manifest.write_text(clean.replace('adapter = "drafting"\n', ""))
    assert "but no credential names it" in rig.run("check").stderr
    manifest.write_text(clean)
    (rig.root / "app.py").write_text(f'KEY = "{GOOD}"\n')
    done = rig.run("check")
    assert done.returncode == 1 and "app.py:1: looks like a key for Anthropic" in done.stderr
    (rig.root / ".gitignore").write_text("app.py\n")
    assert rig.run("check").returncode == 0, "an ignored file is never committed, so it is not a leak"


def test_provision_probes_stores_and_never_prints():
    rig = Rig()
    rig.clipboard(GOOD, RAILWAY)
    done = rig.run("provision", "--env", "staging", "--no-open", enters=2)
    assert done.returncode == 0, done.stderr
    anthropic = rig.fake.secrets[("staging", "/worker", "ANTHROPIC_API_KEY")]
    railway = rig.fake.secrets[("staging", "/ops", "RAILWAY_STAGING_TOKEN")]
    assert anthropic["secretValue"] == GOOD and railway["secretValue"] == RAILWAY
    meta = {m["key"]: m["value"] for m in anthropic["secretMetadata"]}
    assert meta["minted_at"] == dt.datetime.now(dt.UTC).date().isoformat() and len(meta["fingerprint"]) == 12
    assert anthropic["secretReminderRepeatDays"] == 90
    assert {("staging", "/worker"), ("staging", "/ops")} <= rig.fake.folders
    assert "environment env-stg" in done.stdout, "the railway probe shows which environment the token controls"
    assert "Give it an expiry of 90 days" in done.stdout
    assert rig.cleared.read_text().count("cleared") == 2
    again = rig.run("provision", "--env", "staging", "--no-open")
    assert again.returncode == 0 and again.stdout.count("present") == 2 and len(rig.writes()) == 2


def test_a_key_that_fails_or_is_misshapen_stores_nothing():
    rig = Rig()
    rig.clipboard(WRONG)
    done = rig.run("provision", "--env", "prod", "--no-open", enters=1)
    assert done.returncode != 0 and "did not work" in done.stderr and not rig.writes()
    rig.clipboard("hello there")
    done = rig.run("provision", "--env", "prod", "--no-open", enters=1)
    assert "more than one word" in done.stderr and not rig.writes()
    rig.clipboard("sk-not-anthropic")
    done = rig.run("provision", "--env", "prod", "--no-open", enters=1)
    assert "do not look like a key for Anthropic" in done.stderr and not rig.writes()


def test_rotate_patches_and_names_the_old_key():
    rig = Rig()
    rig.clipboard(GOOD)
    assert rig.run("provision", "--env", "prod", "--no-open", enters=1).returncode == 0
    rig.clipboard(GOOD)
    same = rig.run("rotate", "ANTHROPIC_API_KEY", "--env", "prod", "--no-open", enters=1)
    assert same.returncode != 0 and "still holds the key in use" in same.stderr
    rig.clipboard(GOOD_2)
    done = rig.run("rotate", "ANTHROPIC_API_KEY", "--env", "prod", "--no-open", enters=1)
    assert done.returncode == 0, done.stderr
    record = rig.fake.secrets[("prod", "/worker", "ANTHROPIC_API_KEY")]
    assert record["secretValue"] == GOOD_2 and record["version"] == 2
    assert f"ending ...{GOOD[-4:]}" in done.stdout and "keeps version 1" in done.stdout
    assert rig.writes()[-1][0] == "PATCH"


def test_audit_fails_on_missing_and_overdue():
    rig = Rig()
    rig.clipboard(GOOD, RAILWAY)
    rig.run("provision", "--env", "staging", "--no-open", enters=2)
    done = rig.run("audit", "--json", str(rig.root / "audit.json"))
    assert done.returncode == 1 and "missing      ANTHROPIC_API_KEY in prod" in done.stdout
    rig.clipboard(GOOD)
    rig.run("provision", "--env", "prod", "--no-open", enters=1)
    assert rig.run("audit").returncode == 0
    old = (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=120)).isoformat()
    record = rig.fake.secrets[("staging", "/worker", "ANTHROPIC_API_KEY")]
    record["secretMetadata"] = [{"key": "minted_at", "value": old}]
    done = rig.run("audit")
    assert done.returncode == 1 and "overdue" in done.stdout
    report = json.loads((rig.root / "audit.json").read_text())
    assert {r["status"] for r in report["credentials"]} >= {"missing", "ok"}


def test_adopt_records_a_mint_date_for_an_imported_key():
    rig = Rig()
    rig.fake.folders.add(("prod", "/worker"))
    rig.fake.secrets[("prod", "/worker", "ANTHROPIC_API_KEY")] = {"secretValue": GOOD, "version": 1}
    done = rig.run("adopt", "ANTHROPIC_API_KEY", "--env", "prod", "--minted", "2026-10-01")
    assert done.returncode == 0, done.stderr
    meta = {m["key"]: m["value"] for m in rig.fake.secrets[("prod", "/worker", "ANTHROPIC_API_KEY")]["secretMetadata"]}
    assert meta["minted_at"] == "2026-10-01" and len(meta["fingerprint"]) == 12


def test_no_key_over_plain_http_except_to_localhost():
    rig = Rig()
    rig.clipboard(GOOD)
    env = rig.env | {"CREDENTIALS_VENDOR_BASE": "http://example.invalid"}
    done = rig.run("provision", "--env", "prod", "--no-open", enters=1, env=env)
    assert "refusing to send a credential over plain http" in done.stderr and not rig.writes()


TESTS = [
    test_check_refuses_each_mistake_and_a_key_in_the_tree,
    test_provision_probes_stores_and_never_prints,
    test_a_key_that_fails_or_is_misshapen_stores_nothing,
    test_rotate_patches_and_names_the_old_key,
    test_audit_fails_on_missing_and_overdue,
    test_adopt_records_a_mint_date_for_an_imported_key,
    test_no_key_over_plain_http_except_to_localhost,
]

if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"caught  {test.__name__}")
