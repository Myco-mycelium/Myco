# GitHub Repository Setup Guide

This guide walks you through putting Myco on GitHub from scratch. No coding experience needed — just follow each step.

**Need help?** Join the Discord: [discord.gg/NTGWzPy4yB](https://discord.gg/NTGWzPy4yB)

---

## Before you start

You need:
- A [GitHub account](https://github.com/join) (free)
- [Git installed](https://git-scm.com/downloads) on your computer
- Myco downloaded and working on your machine (see [Quick Start](quick-start.md))

---

## Step 1 — Run the setup script

This replaces all the placeholder text in the docs with your actual GitHub username.

```bash
cd myco
python3 setup_repo.py
```

It will ask for your GitHub username, then update every file automatically. It also prints your next steps with a freshly-generated parent token.

**What it changes:** Every place the docs say `Myco-mycelium`, it becomes your real username. This affects links in the README, issue templates, workflows, and documentation.

---

## Step 2 — Create the repository on GitHub

1. Go to [github.com/new](https://github.com/new)
2. Fill in:
   - **Repository name:** `myco`
   - **Description:** `A self-growing AI that learns from every interaction — works offline, supports any model, absorbs open-source plugins`
   - **Visibility:** Public (so the community can find it and contribute)
   - **Do NOT tick** "Add a README file" — you already have one
   - **Do NOT tick** "Add .gitignore" — you already have one
   - **Do NOT tick** "Choose a license" — you already have one
3. Click **Create repository**

---

## Step 3 — Push your code

Copy the commands GitHub shows you under "push an existing repository", or use these (replace `YOURUSERNAME` with yours):

```bash
cd myco

# Initialise git
git init

# Stage everything
git add .

# First commit
git commit -m "Initial release: Myco v2.0.0 — a self-growing AI"

# Set main as the default branch
git branch -M main

# Connect to GitHub (replace YOURUSERNAME)
git remote add origin https://github.com/YOURUSERNAME/myco.git

# Push
git push -u origin main
```

If asked for a password, use a **Personal Access Token** (not your GitHub password). Create one at: GitHub → Settings → Developer settings → Personal access tokens → Generate new token. Give it the `repo` scope.

---

## Step 4 — Configure the repository settings

After pushing, go to your repo on GitHub and configure these settings.

### 4a. Repository description and topics

On your repo's main page, click the gear icon ⚙️ next to "About" (top right of the code view).

**Description:**
```
A self-growing AI that learns from every interaction. Works offline, supports any model, absorbs open-source plugins. 🍄
```

**Website:** (leave blank for now, or add your GitHub Pages URL later)

**Topics** (click "Manage topics"):
```
ai machine-learning ollama llm chatbot self-improving offline python fastapi
open-source plugin-system local-ai privacy
```

Topics help people find Myco when searching GitHub.

### 4b. Branch protection (recommended)

Protects the `main` branch from accidental direct pushes.

1. Settings → Branches → Add branch protection rule
2. Branch name pattern: `main`
3. Tick:
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - Search for and add: `Tests (ubuntu-latest / 3.12)`
4. Click **Create**

### 4c. Enable Discussions (optional)

Settings → General → Features → tick **Discussions**

Lets the community post longer conversations without cluttering Issues. Good for "I built X with Myco" posts.

### 4d. Social preview image (recommended)

Settings → General → Social preview → Upload image

This is the image that appears when someone shares your GitHub link on Discord, Twitter, etc. A simple image with the 🍄 logo and "Myco — A digital mind that never stops growing" is enough. Size: 1280×640px.

---

## Step 5 — Add secrets for CI/CD

Your GitHub Actions workflows need these secrets to work fully.

Go to: **Settings → Secrets and variables → Actions → New repository secret**

### DISCORD_WEBHOOK (required for Discord notifications)

1. Open your Discord server
2. Go to a channel (e.g. `#dev` or `#github`)
3. Click the gear ⚙️ → Integrations → Webhooks → New Webhook
4. Name it "Myco CI", pick the channel, copy the URL
5. Add to GitHub as secret named `DISCORD_WEBHOOK`

This enables:
- A message in Discord when tests fail on the main branch
- A release announcement when you publish a new version

### ANTHROPIC_API_KEY (optional — for future testing)

If you want CI tests to test against real AI responses later, add your API key here. Not needed now.

---

## Step 6 — Pin the repository (optional)

If you have multiple repos, pin Myco so it appears first on your GitHub profile:

1. Go to your GitHub profile page
2. Click "Customize your pins"
3. Tick `myco`

---

## Step 7 — Create your first release

Tags create downloadable releases automatically via the `release.yml` workflow.

```bash
# In your myco directory
git tag v2.0.0 -m "Initial public release"
git push origin v2.0.0
```

GitHub Actions will:
1. Run all tests
2. Build a zip archive
3. Create a GitHub Release with download link
4. Post a Discord announcement

Check the **Actions** tab on GitHub to watch it run. First time takes 3–5 minutes.

After it finishes, go to the **Releases** tab — you should see v2.0.0 with the zip attached.

---

## Step 8 — Set up your Discord server for Myco

Before you share the link publicly, set up the Discord channels properly.

Suggested channel structure:

```
📢 ANNOUNCEMENTS
   #announcements    (post-only, for releases and news)
   #changelog        (auto-posts from GitHub via webhook)

💬 COMMUNITY
   #welcome          (pinned: what Myco is, quick start link)
   #general          (anything)
   #showcase         (share what you built with Myco)

🛠 SUPPORT
   #help             (questions and troubleshooting)
   #bugs             (report bugs before opening a GitHub issue)

🧩 PLUGINS
   #plugin-gallery   (share plugins you made)
   #plugin-ideas     (suggest new plugins)

⚙️ DEVELOPMENT
   #dev              (technical discussion, PRs, roadmap)
   #github           (auto-posts from GitHub: commits, PRs, issues)
```

### Connect GitHub to Discord (auto-posts commits and PRs)

1. In `#github` channel → Edit Channel → Integrations → Webhooks → Copy URL
2. On GitHub: Settings → Webhooks → Add webhook
   - Payload URL: paste the Discord webhook URL + `/github`
   - Content type: `application/json`
   - Events: Send me **everything** (or pick: pushes, pull requests, releases)
3. Click **Add webhook**

Now every push and PR posts automatically to your Discord `#github` channel.

---

## Step 9 — Write the first Discord welcome message

Pin this in `#welcome`:

```
👋 Welcome to the Myco community!

Myco is a self-growing AI that runs on your computer. 
It remembers everything, learns from every conversation, 
and can absorb open-source code as new capabilities.

🚀 Get started:
→ Install: github.com/YOURUSERNAME/myco
→ Docs: github.com/YOURUSERNAME/myco/tree/main/docs
→ Quick start: 5 minutes to your first conversation

💬 Channels:
→ #help if something is broken
→ #plugin-gallery to share what you built
→ #general to chat about anything

No question is too basic. We're all learning. 🍄
```

---

## Step 10 — Share it

Once the repo is live and tests are passing, share it:

**Reddit posts (use these titles):**

- r/LocalLLaMA: `Myco — a self-growing AI that runs entirely offline, works on 2GB RAM, and absorbs Python plugins as new capabilities`
- r/selfhosted: `I built a self-improving AI assistant that lives on your machine and grows smarter with every conversation`
- r/artificial: `Myco — an AI that starts knowing almost nothing and genuinely learns over time, works without any API key`

**HackerNews:**

Title: `Show HN: Myco – a self-growing AI that works offline and absorbs open-source code as plugins`

First paragraph should explain what makes it different (offline, self-improving, plugin system) and link to the GitHub repo.

---

## Checklist

Before posting anywhere, run through this:

- [ ] `python3 setup_repo.py` completed — no more `Myco-mycelium` in any file
- [ ] `.env` created with `MYCO_PARENT_TOKEN` set
- [ ] `git push -u origin main` succeeded
- [ ] GitHub Actions → all 3 jobs are green ✅
- [ ] First release tag pushed: `git tag v2.0.0 && git push origin v2.0.0`
- [ ] Release appeared under the Releases tab
- [ ] Discord `DISCORD_WEBHOOK` secret added to GitHub
- [ ] Repository description and topics added on GitHub
- [ ] Discord channels set up with #welcome pinned
- [ ] Tested the Quick Start guide on a second machine (or fresh VM)

---

## After the first users arrive

When people start opening issues and asking questions:

1. **Answer within 24 hours** — even if the answer is "I don't know yet, let me look into it". Response time matters more than the quality of the answer for building trust.

2. **Label issues properly** — GitHub's issue labels help people find what is known and what is being worked on. Use: `bug`, `enhancement`, `question`, `good first issue`, `help wanted`, `documentation`.

3. **Mark good first issues** — label easy issues with `good first issue`. GitHub shows these on the contributing page and they attract new contributors.

4. **Thank people** — when someone opens a good bug report or makes a PR, thank them by name. It costs nothing and builds community.

5. **Keep a changelog** — every time you fix something or add a feature, add a line to `CHANGELOG.md` before pushing. Tells users what changed and why.
