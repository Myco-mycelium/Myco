#!/usr/bin/env python3
"""
setup_repo.py
=============
Run this ONCE after cloning to personalise Myco for your GitHub account.

Usage:
    python3 setup_repo.py

It will ask for your GitHub username and replace all placeholder text
throughout the documentation and config files.
"""

import os
import sys

PLACEHOLDER = "yourusername"

FILES_TO_UPDATE = [
    "README.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    ".github/CODEOWNERS",
    ".github/SUPPORT.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".github/ISSUE_TEMPLATE/question.md",
    ".github/ISSUE_TEMPLATE/plugin_share.md",
    ".github/workflows/release.yml",
    "docs/index.md",
    "docs/installation.md",
    "docs/quick-start.md",
    "docs/contributing.md",
    "docs/security.md",
    "docs/roadmap.md",
    "docs/faq.md",
    "docs/troubleshooting.md",
    "docs/api-reference.md",
    "docs/github-setup.md",
]


def main():
    print()
    print("🍄  Myco — Repository Setup")
    print("=" * 40)
    print()

    # Get GitHub username
    username = input("Your GitHub username (e.g. johndoe): ").strip()
    if not username:
        print("No username entered. Exiting.")
        sys.exit(1)

    # Validate
    if " " in username or "/" in username:
        print("That does not look like a GitHub username. Exiting.")
        sys.exit(1)

    print()
    print(f"Replacing '{PLACEHOLDER}' → '{username}' in documentation...")
    print()

    updated = 0
    skipped = 0

    for filepath in FILES_TO_UPDATE:
        if not os.path.exists(filepath):
            print(f"  SKIP  {filepath} (file not found)")
            skipped += 1
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()

        if PLACEHOLDER not in original:
            print(f"  OK    {filepath} (no placeholder found)")
            continue

        updated_content = original.replace(PLACEHOLDER, username)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated_content)

        count = original.count(PLACEHOLDER)
        print(f"  DONE  {filepath} ({count} replacement{'s' if count != 1 else ''})")
        updated += 1

    print()
    print(f"Updated {updated} file(s). Skipped {skipped} missing file(s).")
    print()

    # Parent token reminder
    print("Next steps:")
    print()
    print("  1. Copy the environment template:")
    print("     cp .env.example .env")
    print()
    print("  2. Generate a parent token and add it to .env:")
    import secrets
    token = secrets.token_urlsafe(32)
    print(f"     MYCO_PARENT_TOKEN={token}")
    print("     (this is a freshly generated example — use this one or make your own)")
    print()
    print("  3. Optional — add an AI model API key to .env:")
    print("     ANTHROPIC_API_KEY=sk-ant-...")
    print("     Or install Ollama: https://ollama.com")
    print()
    print("  4. Start Myco:")
    print("     pip install -r requirements.txt")
    print("     python -m api.main")
    print()
    print("  5. Open http://localhost:8000")
    print()
    print("  6. Push to GitHub:")
    print(f"     git init")
    print(f"     git add .")
    print(f"     git commit -m 'Initial release: Myco v2.0.0'")
    print(f"     git branch -M main")
    print(f"     git remote add origin https://github.com/{username}/myco.git")
    print(f"     git push -u origin main")
    print()
    print("  7. Add Discord webhook to GitHub for CI notifications:")
    print("     GitHub → Settings → Secrets → Actions → New secret")
    print("     Name: DISCORD_WEBHOOK")
    print("     Value: (your Discord webhook URL)")
    print()
    print("🍄  Done! Myco is ready to grow.")
    print()


if __name__ == "__main__":
    main()
