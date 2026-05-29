"""Pure parser for `claude -p --output-format stream-json` output.

No grading logic, no I/O beyond an optional file read. Extracts the final
assistant prose and the ordered list of tool calls from the JSONL event stream.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ToolCall:
    name: str
    input: dict


@dataclass(frozen=True)
class Transcript:
    final_prose: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    def called(self, tool_suffix: str) -> bool:
        """True if any tool whose name ends with ``tool_suffix`` was called.

        Lets checks match on the bare endpoint (``macro_analyst``) without the
        ``mcp__claude_ai_Parallax__`` namespace prefix.
        """
        return any(c.name.endswith(tool_suffix) for c in self.tool_calls)


def parse_stream_json(raw: str) -> Transcript:
    final_prose = ""
    tool_calls: list[ToolCall] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "assistant":
            content = (event.get("message") or {}).get("content") or []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append(
                        ToolCall(name=block.get("name", ""), input=block.get("input") or {})
                    )
        elif etype == "result":
            # The result event carries the final assistant text. Last non-null
            # result wins (the final result event is authoritative), even if
            # the CLI ever emits an empty string to signal truncation.
            result_val = event.get("result")
            if result_val is not None:
                final_prose = result_val
    return Transcript(final_prose=final_prose, tool_calls=tool_calls)


def load_transcript(path: str | Path) -> Transcript:
    return parse_stream_json(Path(path).read_text())
