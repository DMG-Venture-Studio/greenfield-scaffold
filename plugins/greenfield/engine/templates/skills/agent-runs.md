---
name: agent-runs
description: Trace, score and baseline agent runs with agent-house. Use when changing an agent, a prompt, an agent tool or a model adapter, or before claiming an agent got faster or cheaper.
---

# Agent runs: trace every run, score it, hold the score

A claim that an agent got better is a number from a recorded run, never a reading of the code. This
project records runs as OpenTelemetry traces and scores them with agent-house, which ranks fixes by
estimated cost and latency saved: duplicate tool calls, calls that could run in parallel, uncached
prompts, oversized context, retry loops, a frontier model on a trivial step.

## Where spans come from

Every model call goes through an adapter, the one module allowed to import the model SDK, so the adapter
is where each call becomes a span. Set the GenAI attributes agent-house reads:

```
a model call   gen_ai.operation.name = "chat", gen_ai.system ("anthropic"), gen_ai.request.model,
               gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.usage.cache_read_input_tokens
a tool call    gen_ai.operation.name = "execute_tool", gen_ai.tool.name (the tool, <noun>_<verb>),
               gen_ai.tool.input
the run        one root span, gen_ai.operation.name = "invoke_agent"
```

The adapters import `opentelemetry-api`; the tests that record traces add `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-common` and `protobuf` to the dev group.

## Scenarios

Each agent behaviour that matters is a scenario in `tests/agent_runs/<scenario>/`: the input,
`trace.json` (a recorded run in OTLP/JSON) and `baseline.json` (the accepted report).

Write a trace from a test run with an in-memory exporter:

```python
import base64
import json
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import ReadableSpan


def write_trace(spans: tuple[ReadableSpan, ...], path: Path) -> None:
    """OTLP/JSON for finished spans, ids in hex as the OTLP JSON encoding requires."""
    doc = MessageToDict(encode_spans(spans))
    for resource in doc.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                for key in ("traceId", "spanId", "parentSpanId"):
                    if key in span:
                        span[key] = base64.b64decode(span[key]).hex()
    path.write_text(json.dumps(doc, indent=1))
```

Collect the spans with `InMemorySpanExporter` behind a `SimpleSpanProcessor`, run the scenario, then
`write_trace(exporter.get_finished_spans(), path)`.

## Score and hold

```
npx -y agent-house@0.1.2 run tests/agent_runs/<scenario>/trace.json --json report.json --out report.html
npx -y agent-house@0.1.2 ci tests/agent_runs/<scenario>/trace.json \
    --baseline tests/agent_runs/<scenario>/baseline.json --min-score 80
```

`ci` exits non-zero when the score falls below 80 or below the baseline. That is the agent-runs check in
`CONSTRAINTS.md`.

## Rules

- A trace comes from a real or replayed run, never written by hand.
- The baseline moves only in a commit that gives the before and after scores and says why.
- agent-house prices calls from its own table, and an unknown model id prices at zero, so its cost
  category says nothing for that model. Keep the request model attribute to the provider's real id, and check
  `Run: ... est. $` in the output before quoting a saving.
- The savings are estimates and can overlap; the per-run tokens and duration are exact.
- For designing the agent itself (context assembly, evals, guards, trace capture), use the agentwright
  plugin's skills when it is installed.
