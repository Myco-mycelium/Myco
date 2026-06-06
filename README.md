<div align="center">
  <h1>🍄 Myco</h1>
  <p><strong>A digital mind that never stops growing.</strong></p>

  [![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://python.org)
  [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
  [![Works Offline](https://img.shields.io/badge/offline-fully%20functional-orange.svg)](https://github.com/Myco-mycelium/Myco/tree/main/myco_github_release/myco/docs/offline-mode.md)
  [![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da.svg)](https://discord.gg/NTGWzPy4yB)

  <br>
  <strong>Myco is now <em>community-driven</em></strong>
</div>

---

## About Myco

Myco is a self-growing AI entity that starts with almost zero knowledge and learns from every interaction, document, and experience. It remembers everything, improves itself, and can absorb open-source code as new capabilities — all while running on very modest hardware with full offline support.

> **Note from the creator:**  
> My Linux machine unfortunately died, so I am currently unable to actively develop Myco. The project is now in the hands of the community. You are warmly invited to fork it, improve it, adapt it, and make it run even better on any machine that can install software. The code was initially written by me as a beginner, then heavily organized and documented with AI assistance to make it clean and understandable.

---

### Quick Start

```bash
# Clone the repo
git clone https://github.com/Myco-mycelium/Myco.git
cd Myco/myco_github_release/myco

# Install dependencies
pip install -r requirements.txt

# (Optional) Run a small local model
ollama pull qwen2.5:1.5b

# Run Myco
python -m api.main
