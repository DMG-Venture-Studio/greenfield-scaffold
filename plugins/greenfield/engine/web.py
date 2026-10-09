"""The web front end: the same nouns one level up, with its boundaries, names, lint and types checked."""

from __future__ import annotations

import json
from pathlib import Path

from intake import Project

STARTERS = Path(__file__).parent / "starters" / "web"

PACKAGE = {
    "private": True,
    "type": "module",
    "scripts": {
        "check": "tsc -p . && depcruise src --config .dependency-cruiser.cjs && ls-lint && biome check src && knip",
        # npx keeps openapi-typescript (TypeScript 5 peer) out of the tree that pins TypeScript 6
        "api": "npx --yes openapi-typescript@7.13.0 ../openapi.json -o src/generated/api.ts",
    },
    "devDependencies": {
        "@biomejs/biome": "2.5.15",
        "@ls-lint/ls-lint": "2.3.1",
        "dependency-cruiser": "18.5.0",
        "knip": "6.40.0",
        "typescript": "6.0.3",
    },
}

TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022",
        "module": "ESNext",
        "moduleResolution": "Bundler",
        "strict": True,
        "jsx": "react-jsx",
        "noEmit": True,
        "skipLibCheck": True,
    },
    "include": ["src"],
}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _noun_files(name: str, title: str, path: str) -> dict[str, str]:
    base, camel = f"web/src/nouns/{name}", _camel(name)
    return {
        f"{base}/api.ts": f'import {{ call }} from "../../kernel/http";\n\n'
        f'export const request{title} = (key: string) => call("{path}", {{ key }});\n',
        f"{base}/state.ts": f'import {{ request{title} }} from "./api";\n\n'
        f"export const use{title} = (key: string) => request{title}(key);\n",
        f"{base}/ui.ts": 'import { spacing } from "../../kernel/design";\n'
        f'import {{ use{title} }} from "./state";\n\n'
        f"export const {title}Card = (key: string) => ({{ data: use{title}(key), gap: spacing.small }});\n",
        f"{base}/routes.ts": f'import {{ {title}Card }} from "./ui";\n\n'
        f'export const {camel}Routes = [{{ path: "/{name}/:key", render: {title}Card }}];\n',
    }


def files(p: Project) -> dict[str, str]:
    """Every web file, by path from the project root; empty without a web surface."""
    if not p.web:
        return {}
    nouns = p.screen_nouns
    paths = {n.name: "/" + n.operations[0].replace(".", "/") for n in nouns}
    out: dict[str, str] = {}
    for n in nouns:
        out |= _noun_files(n.name, n.title, paths[n.name])
    imports = "".join(f'import {{ {_camel(n.name)}Routes }} from "../nouns/{n.name}/routes";\n' for n in nouns)
    spread = ", ".join(f"...{_camel(n.name)}Routes" for n in nouns)
    entries = "".join(
        f'  "/{op.replace(".", "/")}": {{ post: {{ body: {{ key: string }} }} }};\n'
        for n in nouns
        for op in n.operations
    )
    package = {"name": f"{p.slug}-web", **PACKAGE}
    out |= {
        "web/package.json": json.dumps(package, indent=2) + "\n",
        "web/tsconfig.json": json.dumps(TSCONFIG, indent=2) + "\n",
        "web/src/main.ts": 'import { routes } from "./app/routes";\n\nexport default routes;\n',
        "web/src/app/routes.ts": f"{imports}\nexport const routes = [{spread}];\n",
        "web/src/kernel/http.ts": 'import type { paths } from "../generated/api";\n\n'
        "export async function call<P extends keyof paths>(path: P, body: unknown): Promise<unknown> {\n"
        '\tconst response = await fetch(path, { method: "POST", body: JSON.stringify(body) });\n'
        "\treturn response.json();\n}\n",
        "web/src/kernel/design.ts": "export const spacing = { small: 4, medium: 8 } as const;\n",
        "web/src/generated/api.ts": "// Placeholder from project-spec.toml until the http surface publishes "
        "openapi.json;\n"
        "// then `npm run api` regenerates this file and the client drift check holds it. Do not edit.\n"
        f"export interface paths {{\n{entries}}}\n",
        "web/plants.toml": plants(p),
    }
    for name in (".dependency-cruiser.cjs", ".ls-lint.yml", "biome.json"):
        out[f"web/{name}"] = (STARTERS / name).read_text()
    return out


def _plant(label: str, file: str, how: str, text: str, check: str, says: str) -> str:
    return (
        f"[[plant]]\nlabel = {json.dumps(label)}\nfile = {json.dumps(file)}\n{how} = {json.dumps(text)}\n"
        f"expect = {{ check = {json.dumps(check)}, says = {json.dumps(says)} }}\n"
    )


def _plant_edits(label: str, edits: list[tuple[str, str, str]], check: str, says: str) -> str:
    rows = ",\n".join(f"  {{ file = {json.dumps(f)}, {h} = {json.dumps(t)} }}" for f, h, t in edits)
    return (
        f"[[plant]]\nlabel = {json.dumps(label)}\nedits = [\n{rows},\n]\n"
        f"expect = {{ check = {json.dumps(check)}, says = {json.dumps(says)} }}\n"
    )


def plants(p: Project) -> str:
    """The front end's plants, run from the repository root against web/."""
    nouns = p.screen_nouns
    n = nouns[0]
    base, camel, title = f"src/nouns/{n.name}", _camel(n.name), n.title
    head = (
        "# The planted violations for the front end. From the repository root:\n"
        "#   uv run python tools/toolkit/prove_checks.py web/plants.toml\n\n"
        '[[check]]\nname = "boundaries"\n'
        'run = ["npx", "depcruise", "src", "--config", ".dependency-cruiser.cjs", "--output-type", "err"]\n\n'
        '[[check]]\nname = "names"\nrun = ["npx", "ls-lint"]\n\n'
        '[[check]]\nname = "lint"\nrun = ["npx", "biome", "lint", "src"]\n\n'
        '[[check]]\nname = "types"\nrun = ["npx", "tsc", "-p", "."]\n\n'
    )
    rows = [
        _plant(
            "the kernel imports a noun",
            "src/kernel/design.ts",
            "append",
            f'import {{ {camel}Routes }} from "../nouns/{n.name}/routes";\nexport const y = {camel}Routes;\n',
            "boundaries",
            "tiers-kernel-is-the-floor",
        ),
        _plant(
            "a noun imports the app",
            f"{base}/ui.ts",
            "append",
            'import { routes } from "../../app/routes";\nexport const w = routes;\n',
            "boundaries",
            "tiers-nouns-never-import-the-app",
        ),
        _plant(
            "the app calls a noun's api directly",
            "src/app/routes.ts",
            "append",
            f'import {{ request{title} }} from "../nouns/{n.name}/api";\nexport const v = request{title};\n',
            "boundaries",
            "app-reaches-nouns-through-routes-and-ui",
        ),
        _plant(
            "the api role imports state",
            f"{base}/api.ts",
            "append",
            f'import {{ use{title} }} from "./state";\nexport const u = use{title};\n',
            "boundaries",
            "roles-api-is-the-bottom",
        ),
        _plant(
            "ui touches the generated client",
            f"{base}/ui.ts",
            "append",
            'import type { paths } from "../../generated/api";\nexport type P = paths;\n',
            "boundaries",
            "one-network-path",
        ),
        _plant(
            "a raw fetch inside a noun",
            f"{base}/state.ts",
            "append",
            'export const raw = () => fetch("/x");\n',
            "lint",
            "noRestrictedGlobals",
        ),
        _plant(
            "a file outside the role vocabulary",
            f"{base}/helpers.ts",
            "create",
            "export const helper = 1;\n",
            "names",
            "helpers.ts",
        ),
        _plant(
            "a file nothing imports",
            "src/kernel/auth.ts",
            "create",
            "export const token = 1;\n",
            "boundaries",
            "no-orphans",
        ),
        _plant(
            "explicit any", f"{base}/state.ts", "append", "export const s = (x: any) => x;\n", "lint", "noExplicitAny"
        ),
        _plant(
            "a type error", f"{base}/state.ts", "append", 'export const wrong: number = "text";\n', "types", "TS2322"
        ),
    ]
    rows += [
        _plant(
            "the state role imports ui",
            f"{base}/state.ts",
            "append",
            f'import {{ {title}Card }} from "./ui";\nexport const q = {title}Card;\n',
            "boundaries",
            "roles-state-below-ui",
        ),
        _plant(
            "the ui role imports routes",
            f"{base}/ui.ts",
            "append",
            f'import {{ {camel}Routes }} from "./routes";\nexport const r = {camel}Routes;\n',
            "boundaries",
            "roles-ui-below-routes",
        ),
        _plant(
            "a dev dependency imported by the product",
            "src/kernel/design.ts",
            "append",
            'import ts from "typescript";\nexport const t = ts;\n',
            "boundaries",
            "no-dev-dependencies-in-src",
        ),
        _plant(
            "console in product code",
            f"{base}/state.ts",
            "append",
            "export const log = () => console.log(1);\n",
            "lint",
            "noConsole",
        ),
    ]
    other = nouns[1].name if len(nouns) > 1 else "probe"
    edits = [(f"{base}/state.ts", "append", f'import {{ z }} from "../{other}/state";\nexport const y2 = z;\n')]
    if len(nouns) > 1:
        edits.append((f"src/nouns/{other}/state.ts", "append", "export const z = 1;\n"))
    else:
        edits.append((f"src/nouns/{other}/state.ts", "create", "export const z = 1;\n"))
    rows.insert(0, _plant_edits("a noun imports another noun", edits, "boundaries", "nouns-are-independent"))
    return head + "\n".join(rows)
