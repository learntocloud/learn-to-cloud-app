#!/usr/bin/env python3
"""Parse Copilot chat session logs and report token usage per turn."""
import json
import os
import sys

def main():
    session_dir = os.path.expanduser(
        "~/Library/Application Support/Code/User/workspaceStorage/"
        "196a36d5550f32b74607b537427e9590/chatSessions"
    )

    # Find most recent .jsonl file (current session)
    if len(sys.argv) > 1:
        logfile = sys.argv[1]
    else:
        files = [
            os.path.join(session_dir, f)
            for f in os.listdir(session_dir)
            if f.endswith(".jsonl")
        ]
        logfile = max(files, key=os.path.getmtime)

    print(f"Session: {os.path.basename(logfile)}")
    print(f"Size: {os.path.getsize(logfile):,} bytes\n")

    with open(logfile) as f:
        lines = [json.loads(l) for l in f]

    print(f"{'Turn':<6} {'Prompt':>10} {'Output':>10} {'Total':>10} | Breakdown")
    print("-" * 100)

    total_prompt = 0
    total_output = 0
    turn = 0

    for entry in lines:
        v = entry.get("v", {})
        if not isinstance(v, dict):
            continue
        usage = v.get("usage")
        if not usage or not isinstance(usage, dict):
            continue

        turn += 1
        pt = usage.get("promptTokens", 0)
        ct = usage.get("completionTokens", 0)
        total_prompt += pt
        total_output += ct

        details = usage.get("promptTokenDetails", [])
        parts = []
        for d in details:
            label = d.get("label", "?")
            pct = d.get("percentageOfPrompt", 0)
            parts.append(f"{label}={pct}%")
        breakdown = ", ".join(parts) if parts else "no breakdown"

        print(f"T{turn:<5} {pt:>10,} {ct:>10,} {pt+ct:>10,} | {breakdown}")

    print("-" * 100)
    print(f"{'SUM':<6} {total_prompt:>10,} {total_output:>10,} {total_prompt+total_output:>10,}")
    print(f"Turns: {turn}")
    print(f"Avg prompt/turn: {total_prompt//max(turn,1):,}")
    print(f"Peak prompt: {max((e.get('v',{}).get('usage',{}).get('promptTokens',0) for e in lines if isinstance(e.get('v',{}), dict) and isinstance(e.get('v',{}).get('usage'), dict)), default=0):,}")
    print(f"Context window: 935,805 (Claude Opus 4.6 1M)")
    peak = max(
        (e.get("v",{}).get("usage",{}).get("promptTokens",0)
         for e in lines
         if isinstance(e.get("v",{}), dict) and isinstance(e.get("v",{}).get("usage"), dict)),
        default=0,
    )
    print(f"Peak utilization: {peak*100/935805:.1f}%")

if __name__ == "__main__":
    main()
