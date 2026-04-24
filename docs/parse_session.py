#!/usr/bin/env python3
"""Parse a Claude Code JSONL session file into a readable markdown document."""

import json
import sys
from datetime import datetime

INPUT = "/Users/jkarnik/.claude/projects/-Users-jkarnik-Code-Topology-Maps/f030c4ac-f63f-41c8-b62a-0afae6c8fb5e.jsonl"
OUTPUT = "/Users/jkarnik/Code/Topology Maps/docs/session-f030c4ac.md"

TOOL_SUMMARY = {
    "Read": lambda i: f"Read `{i.get('file_path','?')}`",
    "Write": lambda i: f"Write `{i.get('file_path','?')}`",
    "Edit": lambda i: f"Edit `{i.get('file_path','?')}`",
    "Bash": lambda i: f"Run: `{i.get('command','?')[:120]}`",
    "Glob": lambda i: f"Glob `{i.get('pattern','?')}`",
    "Grep": lambda i: f"Grep `{i.get('pattern','?')}` in `{i.get('path','.')}`",
    "TodoWrite": lambda i: f"Update todo list ({len(i.get('todos',[]))} items)",
    "Agent": lambda i: f"Spawn agent: {i.get('description','?')[:80]}",
    "WebFetch": lambda i: f"Fetch `{i.get('url','?')[:80]}`",
    "WebSearch": lambda i: f"Search: `{i.get('query','?')}`",
}

def fmt_time(ts):
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except:
        return ts or ""

def extract_text(content):
    """Extract only text blocks from a content array."""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            t = block.get("text", "").strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts)

def extract_tools(content):
    """Summarise tool_use blocks."""
    tools = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            name = block.get("name", "?")
            inp = block.get("input", {})
            fn = TOOL_SUMMARY.get(name)
            if fn:
                try:
                    tools.append(fn(inp))
                except:
                    tools.append(f"{name}(...)")
            else:
                tools.append(f"{name}(...)")
    return tools

def main():
    with open(INPUT) as f:
        lines = f.readlines()

    messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except:
            continue

        mtype = msg.get("type")
        ts = msg.get("timestamp", "")

        if mtype == "user":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, str):
                text = content.strip()
            else:
                text = extract_text(content)
            if text:
                messages.append({"role": "user", "text": text, "ts": ts, "tools": []})

        elif mtype == "assistant":
            content = msg.get("message", {}).get("content", [])
            text = extract_text(content)
            tools = extract_tools(content)
            if text or tools:
                messages.append({"role": "assistant", "text": text, "ts": ts, "tools": tools})

    # Write markdown
    with open(OUTPUT, "w") as out:
        out.write("# Session Export: Topology Maps — April 2026\n\n")
        out.write(f"**Source:** `f030c4ac-f63f-41c8-b62a-0afae6c8fb5e.jsonl`  \n")
        out.write(f"**Messages:** {len(messages)} (user + assistant)  \n")
        out.write(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n")
        out.write("---\n\n")

        turn = 0
        for msg in messages:
            role = msg["role"]
            ts = fmt_time(msg["ts"])
            text = msg["text"]
            tools = msg["tools"]

            if role == "user":
                turn += 1
                out.write(f"## Turn {turn} — User  \n")
                out.write(f"*{ts}*\n\n")
                out.write(f"{text}\n\n")
            else:
                out.write(f"### Assistant  \n")
                out.write(f"*{ts}*\n\n")
                if text:
                    out.write(f"{text}\n\n")
                if tools:
                    out.write("**Actions taken:**\n")
                    for t in tools:
                        out.write(f"- {t}\n")
                    out.write("\n")
            out.write("---\n\n")

    print(f"Written {len(messages)} messages to {OUTPUT}")

if __name__ == "__main__":
    main()
