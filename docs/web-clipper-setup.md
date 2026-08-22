# Obsidian Web Clipper → Inbox

1. Install the Obsidian Web Clipper browser extension.
2. Set the vault to your **vault directory** (`$WIKI_VAULT`, e.g. `~/workspace/personal-wiki/wiki-vault`;
   NOT this code repo) and the default save location to `00_Inbox/browser-clips/`.
3. Use a Markdown template that includes a frontmatter block:
   - `type: source`
   - `origin: browser`
   - `sensitivity: personal`
   - `url: {{url}}`
   - `captured_at: {{date}}`
4. Clip a page; it lands in `00_Inbox/browser-clips/`. In the Chat tab, say
   "Inbox의 새 브라우저 클립 인제스트해줘" to run the ingest subagent over it.
