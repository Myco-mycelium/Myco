# Plugin System

Plugins give Myco new capabilities. Any Python code can become a plugin — tools Myco uses in conversation, or visual panels that appear in the UI. Plugins are sandbox-tested before they run, and you can approve or reject them before they touch anything.

---

## What plugins can do

### Tool plugins
Define Python functions. Myco calls them during chat when useful.

```python
def summarize(text: str) -> str:
    """Summarize text to the 3 most important sentences."""
    sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20]
    return '. '.join(sentences[:3]) + ('.' if sentences else '')

def count_words(text: str) -> int:
    """Count the number of words in text."""
    return len(text.split())
```

After installing, Myco can use `summarize()` and `count_words()` in any conversation automatically.

### Viewer plugins
Set `UI_WIDGET` to an HTML string. It renders as a live panel in the UI.

```python
UI_WIDGET = """
<div style="padding:16px;font-family:system-ui">
  <h3>My Custom Panel</h3>
  <canvas id="myCanvas" width="300" height="200"></canvas>
  <script>
    const ctx = document.getElementById('myCanvas').getContext('2d');
    ctx.fillStyle = '#6ab4f0';
    ctx.fillRect(50, 50, 200, 100);
  </script>
</div>
"""
```

### Combined plugins
A plugin can have both tool functions and a `UI_WIDGET`:

```python
UI_WIDGET = """<div id="result-panel">...</div>"""

def process_data(data: str) -> str:
    """Process data and update the panel."""
    # ... your logic ...
    return "processed"
```

---

## Installing a plugin

### From the UI (recommended)

1. Click **Plugins** in the sidebar
2. Click **Add Plugin**
3. Choose your source:
   - **Paste code** — paste Python directly
   - **GitHub URL** — paste a GitHub file or repo URL
   - **Upload .py file** — drag or browse to a `.py` file
4. Fill in a name and description
5. Click **Preview first** to see what it will add without installing
6. Click **Test in sandbox & install**

### From the API

```bash
curl -X POST http://localhost:8000/plugins/install \
  -H "Authorization: Bearer YOUR_PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Plugin",
    "description": "Does something useful",
    "plugin_type": "tool",
    "code": "def my_tool(x: str) -> str:\n    return x.upper()"
  }'
```

---

## Merging from GitHub

Myco can absorb any public GitHub Python file or repository:

1. Click **Plugins → Add Plugin → GitHub URL**
2. Paste one of:
   - A direct file link: `https://github.com/user/repo/blob/main/module.py`
   - A raw file URL: `https://raw.githubusercontent.com/user/repo/main/module.py`
   - A repo URL: `https://github.com/user/repo` (Myco tries `main.py`, `app.py`, `__init__.py`)
3. Click **Preview** to see what functions and dependencies it has
4. Click **Install** — Myco fetches, sandboxes, and installs

### What Myco does during a merge

1. **Fetches** the code from GitHub
2. **Previews** — shows functions found, dependencies, any security violations
3. **Installs safe dependencies** automatically (from a whitelist of ~30 trusted packages)
4. **Runs static analysis** — rejects banned patterns (imports, exec, file access, network)
5. **Runs in subprocess sandbox** — isolated process with resource limits
6. **Screens output** — checks for leaked secrets or unexpected network calls
7. **Reports result** — shows what tools were added and whether a UI panel was found

---

## Writing your own plugins

### Rules

1. **No imports at module level** — the sandbox blocks `import` and `from ... import`
2. **Use only safe builtins** — `len`, `str`, `int`, `list`, `dict`, `range`, `sorted`, `sum`, etc.
3. **Functions must be synchronous** — no `async def`
4. **Keep it under 8,000 characters** — longer code is rejected
5. **Return strings or simple types** — Myco expects string output from tool calls

### Safe builtins you can use

```python
abs, all, any, bin, bool, chr, complex, divmod, enumerate,
filter, float, format, frozenset, hex, int, isinstance,
issubclass, len, list, map, max, min, oct, ord, pow, print,
range, reversed, round, set, slice, sorted, str, sum, tuple, zip,
dict, True, False, None, Exception, ValueError, TypeError
```

### Pattern: text processing tool

```python
def extract_emails(text: str) -> str:
    """Find all email addresses in text."""
    import re   # NOTE: imports work inside functions — only module-level is blocked
    # Actually, re is not in safe builtins. Use manual parsing:
    emails = []
    words = text.split()
    for word in words:
        if '@' in word and '.' in word:
            emails.append(word.strip('.,;:'))
    return ', '.join(emails) if emails else 'No emails found'
```

Wait — `import re` inside a function is also blocked. Here is how to do it without imports:

```python
def extract_emails(text: str) -> str:
    """Find all email addresses in text (no imports needed)."""
    emails = []
    for word in text.split():
        word = word.strip('.,;:()"\'')
        if '@' in word and '.' in word.split('@')[-1]:
            emails.append(word)
    return ', '.join(emails) or 'No emails found'
```

### Pattern: data formatter

```python
def format_table(rows_csv: str) -> str:
    """Format comma-separated rows as a text table."""
    rows = [r.split(',') for r in rows_csv.strip().split('\n') if r.strip()]
    if not rows:
        return 'No data'
    widths = [max(len(str(row[i])) for row in rows if i < len(row)) for i in range(len(rows[0]))]
    lines = []
    for row in rows:
        lines.append(' | '.join(str(row[i]).ljust(widths[i]) if i < len(widths) else '' for i in range(len(row))))
    sep = '-+-'.join('-' * w for w in widths)
    lines.insert(1, sep)
    return '\n'.join(lines)
```

### Pattern: viewer with live data

```python
# This creates a panel that shows a real-time clock
UI_WIDGET = """
<div style="padding:20px;font-family:system-ui;text-align:center">
  <div style="font-size:48px;font-weight:300;color:#3a2e28" id="clock"></div>
  <div style="font-size:14px;color:#8a7068;margin-top:8px" id="date"></div>
  <script>
    function update() {
      const now = new Date();
      document.getElementById('clock').textContent =
        now.toLocaleTimeString('en-GB');
      document.getElementById('date').textContent =
        now.toLocaleDateString('en-GB', {weekday:'long',year:'numeric',month:'long',day:'numeric'});
    }
    update();
    setInterval(update, 1000);
  </script>
</div>
"""
```

### Pattern: 3D viewer (WebGL)

```python
UI_WIDGET = """
<canvas id="gl" width="400" height="300" style="display:block;background:#111"></canvas>
<script>
  const canvas = document.getElementById('gl');
  // ... WebGL or Three.js code here
  // Note: Three.js can be loaded from cdnjs.cloudflare.com
</script>
"""
```

> **Note:** The viewer runs in a sandboxed `<iframe sandbox="allow-scripts">`. It cannot access the parent page or make network requests. It can load scripts from `cdnjs.cloudflare.com`.

---

## Managing plugins

### From the UI

- **Enable/Disable** — toggle without removing the plugin
- **Remove** — permanently uninstall and delete the plugin code
- **Visual panels** — appear automatically below the installed plugins list

### From the API

```bash
# List all plugins
curl http://localhost:8000/plugins \
  -H "Authorization: Bearer YOUR_TOKEN"

# Disable a plugin
curl -X POST http://localhost:8000/plugins/PLUGIN_ID/toggle \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"enabled": false}'

# Remove a plugin
curl -X DELETE http://localhost:8000/plugins/PLUGIN_ID \
  -H "Authorization: Bearer YOUR_PARENT_TOKEN"

# Preview before installing
curl -X POST http://localhost:8000/merge/preview \
  -H "Authorization: Bearer YOUR_PARENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/repo/blob/main/tool.py", "name": "My Tool"}'
```

---

## Security model

Every plugin goes through 5 layers before it runs:

1. **AST whitelist** — rejects `import`, `exec`, `eval`, dunder access, async functions
2. **String pattern scan** — rejects known dangerous strings (`os.path`, `subprocess`, `/etc/passwd`, etc.)
3. **Subprocess isolation** — code runs in a separate OS process, not the main Myco process
4. **Resource limits** — 3 second wall clock, 2 second CPU, 256 MB RAM, 4 file descriptors
5. **Output screening** — checks output for URLs, credentials, sensitive paths

If any layer rejects the code, it is marked as `REJECTED` and never executes. The result is shown to you in the install UI.

### What is blocked

```python
# BLOCKED — import at module level
import os
import subprocess

# BLOCKED — dunder access
x = obj.__class__.__bases__

# BLOCKED — exec/eval
exec("malicious code")

# BLOCKED — file access
open('/etc/passwd')

# BLOCKED — network
import socket
```

### What is allowed

```python
# Allowed — pure computation
def fibonacci(n: int) -> str:
    a, b = 0, 1
    result = []
    for _ in range(min(n, 50)):
        result.append(a)
        a, b = b, a + b
    return str(result)

# Allowed — string manipulation
def title_case(text: str) -> str:
    return ' '.join(w.capitalize() for w in text.split())

# Allowed — UI widget (HTML/JS only)
UI_WIDGET = "<div>...</div>"
```

---

## Example plugins

Six example plugins are built in to Myco. Install them from **Plugins → Examples**:

| Name | Type | What it does |
|---|---|---|
| Calculator | Tool | Safe evaluation of math expressions |
| Word Analyser | Tool | Word count, sentence count, reading time, vocabulary richness |
| Unit Converter | Tool | Length, weight, temperature conversions |
| JSON Tools | Tool | Format, validate, and table-view JSON |
| Color Explorer | Viewer | Interactive HSL colour picker with live preview |
| 3D Cube Viewer | Viewer | Draggable rotating 3D cube — demonstrates 3D capability |

---

## Troubleshooting plugins

**"Security check failed: Banned node Import"**
Your plugin has `import` at the module level. Move imports inside function bodies — but note that only stdlib modules available as safe builtins will work. Better to rewrite the logic without imports.

**"No callable functions found"**
Myco couldn't find any `def function()` at the top level. Make sure your functions are not indented inside a class or condition.

**Plugin installed but not showing in chat**
Myco uses tools automatically when relevant. Try asking explicitly: `"Use the [tool name] to..."`. Also check the plugin is enabled in the Plugins tab.

**Viewer panel is blank**
Open browser developer tools (F12) and check the console inside the iframe. Common issues: JavaScript syntax error, or trying to load a script from a non-allowed domain.
