#!/usr/bin/env python3
"""
iteration_log.py — Auto-generate iteration logs for development projects

Usage:
    python3 iteration_log.py --project {name} --version {N} --status {status} \
        --reason "{reason}" --changes "{changes}" --session {path} \
        --tokens {N} --runtime {seconds} --files "{paths}" --phase "{phase}"

    python3 iteration_log.py --project my-feature --version 3 --status approved \
        --reason "Approved at Gate 2" --changes "Added refresh token endpoint" \
        --session /path/to/transcript.jsonl --tokens 45000 --runtime 380 \
        --files "auth/routes.py,auth/models.py,migrations/004_add_refresh.py" --phase "execution"

Auto-detects model from session transcript if available.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

VAULT_BASE = os.environ.get("VAULT_BASE", "./projects")
TEMPLATE_PATH = os.environ.get("ITERATION_LOG_TEMPLATE", "./templates/iteration-log-template.md")


def detect_model_from_transcript(transcript_path):
    """Try to detect model from transcript file."""
    if not transcript_path or not os.path.exists(transcript_path):
        return "unknown"

    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if "model" in data:
                        return data["model"]
    except:
        pass
    return "unknown"


def get_or_create_log(project_name):
    """Get existing log path or create new one from template."""
    project_dir = os.path.join(VAULT_BASE, project_name)
    log_path = os.path.join(project_dir, "iteration-log.md")

    if os.path.exists(log_path):
        return log_path

    # Create from template
    template_path = os.path.expanduser(TEMPLATE_PATH)
    if os.path.exists(template_path):
        with open(template_path, 'r') as f:
            content = f.read()
    else:
        # Minimal fallback
        content = "# Iteration Log\n\n## Version History\n\n"

    # Replace placeholders
    content = content.replace("{Project Name}", project_name)
    content = content.replace("{project-name}", project_name)
    content = content.replace("{YYYY-MM-DD}", datetime.now().strftime("%Y-%m-%d"))

    os.makedirs(project_dir, exist_ok=True)
    with open(log_path, 'w') as f:
        f.write(content)

    return log_path


def append_entry(log_path, args):
    """Append a version entry to the log."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    model = args.model or detect_model_from_transcript(args.session)

    entry = f"""\n### v{args.version} ({date_str} {time_str})
- **Model:** {model}
- **Status:** {args.status}
- **Phase:** {args.phase or "N/A"}
- **Trigger:** {args.trigger or args.reason}
- **Reason:** {args.reason}
- **Changes:** {args.changes}
- **Issues found:** {args.issues or "None"}
- **Fix applied:** {args.fix or "N/A (approved)"}
- **Files:** {args.files or "See project directory"}
- **Session:** {args.session or "N/A"}
- **Tokens:** {args.tokens or "N/A"}
- **Runtime:** {args.runtime or "N/A"}s
\n"""

    with open(log_path, 'a') as f:
        f.write(entry)

    return entry


def main():
    parser = argparse.ArgumentParser(description="Generate iteration log entry for development project")
    parser.add_argument("--project", required=True, help="Project name (e.g., my-feature)")
    parser.add_argument("--version", required=True, help="Version number (e.g., 3)")
    parser.add_argument("--status", required=True, choices=["approved", "rejected", "rework", "in-progress", "blocked"])
    parser.add_argument("--phase", default="", help="Pipeline phase (discovery/planning/execution/review/summary)")
    parser.add_argument("--reason", required=True, help="Reason for status")
    parser.add_argument("--changes", default="", help="What changed in this version")
    parser.add_argument("--trigger", default="", help="What triggered this iteration")
    parser.add_argument("--issues", default="", help="Issues found")
    parser.add_argument("--fix", default="", help="Fix applied")
    parser.add_argument("--session", default="", help="Path to session transcript")
    parser.add_argument("--tokens", type=int, default=0, help="Token count")
    parser.add_argument("--runtime", type=int, default=0, help="Runtime in seconds")
    parser.add_argument("--files", default="", help="Comma-separated file paths")
    parser.add_argument("--model", default="", help="Model used (auto-detected if not provided)")

    args = parser.parse_args()

    log_path = get_or_create_log(args.project)
    entry = append_entry(log_path, args)

    print(f"✅ Logged v{args.version} to {log_path}")
    print(entry)


if __name__ == "__main__":
    main()