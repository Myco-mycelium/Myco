# Roadmap

This is what we are working towards. Nothing here is a promise — it is a direction. Priorities can shift based on what the community finds most useful.

Have an idea? Share it on [Discord](https://discord.gg/NTGWzPy4yB) or [open a feature request](https://github.com/Myco-mycelium/myco/issues/new?template=feature_request.md).

---

## Now — what works today (v2.0)

- ✅ Self-growing AI with 7 stages (Seedling → Ancient)
- ✅ Works fully offline — memory, tools, plugins, document ingestion
- ✅ Any AI model: Ollama, Claude, GPT-4o, Gemini, Mistral, custom endpoints
- ✅ Plugin system — absorb any Python code; 3D viewers, charts, tools
- ✅ Open-source merger — paste GitHub URL → Myco absorbs it
- ✅ Self-improvement loop with sandbox + parent approval gate
- ✅ Autonomous learning — detects knowledge gaps, researches them
- ✅ Security sandbox (5 layers), token auth, audit log with hash chain
- ✅ Full desktop-style UI with offline mode banner
- ✅ Mind snapshots and rollback
- ✅ Docker support

---

## Next — what we are working on

These are the things the community has asked for most:

### Better offline responses
Right now the offline brain uses TF-IDF search + intent detection. We want it to be genuinely conversational even without a model — by building a small local response engine on top of the memory.

**How you can help:** Test offline mode and report when it gives bad or confusing answers.

### Memory export and import
Be able to export all memories as a JSON file and import them into another Myco instance. Useful for backups, sharing knowledge bases, and migrating between machines.

**How you can help:** Tell us what format would be most useful.

### Plugin gallery
A community-maintained list of plugins people have built, with one-click install from GitHub. Something like npm but for Myco capabilities.

**How you can help:** Build a plugin and share it on Discord. We will add it to the gallery.

### Mobile-friendly UI
The UI works on phones but is not optimised for small screens. Better touch targets, responsive layout, swipe navigation.

**How you can help:** Test on your phone and report what is hard to use.

### Individual memory cards
View, edit, and delete individual memories from the UI — not just search. Currently you can search but not browse or remove specific items.

**How you can help:** Describe what browsing memories should look like to you.

### Better document ingestion
The current offline ingestion splits by sentence. We want smarter chunking that understands headings, lists, and code blocks — so ingesting a README or tutorial works much better.

**How you can help:** Test ingesting real documents and report what gets stored badly.

---

## Later — bigger ideas

These need more planning and community input before we start:

### Voice input and output
Talk to Myco with a microphone, hear it respond. Uses Whisper for speech-to-text and a local TTS model for speech.

### Image understanding (offline)
Right now image analysis requires a cloud model with vision. We want a lightweight local option — maybe a small CLIP-based model that can describe images without internet.

### Multi-user support
Multiple people sharing one Myco instance, each with their own memory space and conversation history.

### Scheduled tasks
Tell Myco "every Monday morning, summarise what you learned last week". Myco runs tasks on a schedule.

### Plugin marketplace
A proper community hub where people publish and discover plugins, with ratings, reviews, and one-click install.

### Long-term personality development
Myco currently tracks personality traits as simple booleans. We want richer personality modelling — preferences, opinions, communication style — that develop organically through conversations.

### Collaborative learning
Two Myco instances that can share knowledge with each other — so your Myco and a friend's Myco can teach each other.

---

## What we will not build

To keep Myco focused and safe, some things are intentionally out of scope:

- **Cloud hosting / SaaS version** — Myco is designed to run locally. Your data stays yours.
- **Social media integration** — Myco should not automatically post or scrape social media.
- **Financial trading or automation** — too high stakes for autonomous action.
- **Autonomous code deployment** — Myco can write code but should not deploy it without human review.

---

## How priorities are set

1. **Security issues** — always first, no exceptions
2. **Things that are broken** — bug fixes before features
3. **What the community asks for most** — vote on Discord, comment on issues
4. **What the maintainer has time to build** — this is a one-person project; everything takes longer than expected

If something on this list matters to you, say so on Discord or in a GitHub issue. It genuinely changes what gets prioritised.

---

## Contributing to the roadmap

The best way to influence the roadmap:

1. **Use Myco and report what frustrates you** — real friction points > theoretical features
2. **Build a plugin** — shows what is possible and often leads to the plugin system being improved
3. **Help with open issues** — even commenting "I have this problem too" is useful
4. **Join Discord** — roadmap discussions happen there first

---

*Last updated: June 2025*
