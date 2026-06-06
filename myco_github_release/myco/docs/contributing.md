# Contributing to Myco

First of all — **thank you** for wanting to help. Myco is built by someone learning as they go, and every contribution matters, no matter how small. You do not need to be an expert. If you can spot a typo, test something on your machine, or suggest a better way to explain something, that is a real contribution.

This guide explains everything you need to know to get involved.

---

## Who can contribute?

**Everyone.** Seriously. You do not need to know Python, AI, or anything technical to help. Here are things people with different backgrounds can do:

| Background | How you can help |
|---|---|
| No coding experience | Test the app, report bugs, improve documentation, translate |
| A little Python | Fix small bugs, write simple plugins, improve error messages |
| Web developer | Improve the UI, fix CSS, add features to `ui/index.html` |
| AI/ML experience | Improve the memory system, add model support, tune prompts |
| Security experience | Review the sandbox, test for vulnerabilities, improve auth |
| Writer | Improve documentation, write tutorials, translate |
| Designer | Improve the UI design, create icons or diagrams |

---

## Ways to contribute

### 🐛 Report a bug

Found something that does not work? Please tell us! Even if you are not sure it is a bug.

[Open a bug report](https://github.com/Myco-mycelium/myco/issues/new?template=bug_report.md)

What to include:
- What you were doing
- What you expected to happen
- What actually happened
- Your operating system and Python version
- Any error messages (copy-paste them, do not screenshot)

You do not need to fix it yourself — just reporting it is helpful.

---

### 💡 Suggest an improvement

Have an idea for a feature or a better way to do something?

[Open a feature request](https://github.com/Myco-mycelium/myco/issues/new?template=feature_request.md)

---

### 📖 Improve documentation

Found a sentence that is confusing? A step that does not work on your machine? A better way to explain something?

Documentation improvements are some of the most valuable contributions. The files are in the `docs/` folder and are plain Markdown — you can edit them directly on GitHub without downloading anything.

---

### 🔌 Share a plugin

Built a useful plugin? Share it! Open an issue with the code and we can add it to the examples, or write a guide for it.

Plugin ideas that would be very useful:
- Currency converter (fetch live rates)
- Markdown renderer
- Simple note-taking with tags
- Code syntax highlighter
- CSV/spreadsheet viewer
- Simple chart generator

---

### 🌍 Translate

Myco's UI is currently English-only. If you can translate it to another language, open an issue and we will work out the best approach together.

---

## Making code changes

### Step 1 — Fork the repository

Click **Fork** at the top of the GitHub page. This creates your own copy.

### Step 2 — Clone your fork

```bash
git clone https://github.com/YOUR-USERNAME/myco.git
cd myco
```

### Step 3 — Set up your environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 4 — Make your changes

Edit the files you want to change. If you are not sure where to look:
- UI changes → `ui/index.html`
- Chat behaviour → `core/agent.py`
- New tools → `tools/registry.py`
- Configuration → `config/models.yaml`
- Documentation → `docs/*.md`

### Step 5 — Test your changes

```bash
# Run the security tests
python -m pytest safety/tests/ -v

# Start Myco and test manually
python -m api.main
# Open http://localhost:8000 and try your changes
```

### Step 6 — Commit and push

```bash
git add .
git commit -m "Brief description of what you changed"
git push origin main
```

### Step 7 — Open a pull request

Go to your fork on GitHub and click **Compare & pull request**. Describe what you changed and why.

---

## What makes a good pull request?

- **One change per PR** — keeps things easy to review
- **Describe what you changed** and why in the PR description
- **Test it yourself** before opening the PR
- **Keep it small** — a 10-line change is easier to review than 500 lines

Do not worry about being perfect. We can work on it together.

---

## Code style

We do not enforce strict style rules. A few soft guidelines:

- Use clear variable names (`user_input` not `ui`)
- Add a comment when something is not obvious
- Functions should do one thing
- Keep functions short (under 40 lines when possible)
- Match the style of the surrounding code

---

## Running the tests

```bash
# All tests
python -m pytest safety/tests/ -v

# Just security tests
python -m pytest safety/tests/test_security.py -v

# A specific test
python -m pytest safety/tests/test_security.py::TestSandboxExecution::test_simple_function_accepted -v
```

If you add a new feature, try to add a test for it. If you do not know how, open the PR anyway — we can add tests together.

---

## Questions?

If you are stuck or unsure about anything:

1. **Join the Discord server** — [discord.gg/NTGWzPy4yB](https://discord.gg/NTGWzPy4yB) — the fastest way to get help, share what you are building, or just say hello
2. **Open an issue** on GitHub with your question — there are no stupid questions
3. **Look at existing issues** — someone may have asked the same thing
4. **Read the documentation** in `docs/`

We are building this together. Everyone starts somewhere.

---

## Code of conduct

Be kind. That is it. We are all learning. Treat others the way you want to be treated.

Specifically:
- Be patient with beginners (the project creator is one too)
- Welcome different skill levels
- Give constructive feedback, not criticism
- Assume good intentions

---

## Thank you

Seriously — every star, every issue report, every PR, every question helps. You are part of making this better.

Come say hello on Discord: [discord.gg/NTGWzPy4yB](https://discord.gg/NTGWzPy4yB) 🍄
