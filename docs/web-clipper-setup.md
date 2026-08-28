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
4. Clip a page; it lands in `00_Inbox/browser-clips/`. Then in Claude Code say
   "Inbox의 새 브라우저 클립 인제스트해줘". Claude reads `wiki_toolkit/prompts/ingest.md`
   and follows it with the `mcp__wiki__*` tools.
5. 민감한 문서를 클립할 때는 저장 전에 frontmatter의 `sensitivity`를 `work`나
   `confidential`로 바꾼다. ingest 때 이 값이 source로 전달되고, `confidential`만
   원격 임베딩에서 제외된다. ingest 전의 클립은 sensitivity와 무관하게 원격 임베딩에서
   제외된다 (id가 없는 문서는 보내지 않는다). 단, `WIKI_EMBED_SEND_SENSITIVE=1`로
   전체 전송을 켰다면 이 제외도 함께 풀린다.
