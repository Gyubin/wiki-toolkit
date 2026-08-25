# claim에 원문 인용 담기 (Spec)

> 상태: 구현 완료 (2026-08-25)

## 문제

claim 파일 하나만 열면 왜 그 주장이 나왔는지 알 수 없다. 담을 자리가 아예 없기 때문이다.
`create_claim`이 본문을 `f"## Claim\n\n{claim}\n"`으로 고정 생성해서, 본문이 claim 텍스트의
복사본이다. 도구 인자도 `claim, claim_type, source_refs, proposed_status, speaker`뿐이다.

2026-08-25 클립 하나(source-20260825-001, 본문 9932자)를 ingest한 결과를 전수로 재봤다.

| 항목 | 값 |
| --- | --- |
| claim 개수 | 18 |
| claim 길이 | 최소 31자, 중앙 118자, 평균 116자, 최대 247자 |
| 문장 수 | 1문장 8개, 2문장 10개 |
| claim 합계 | 2081자 (원문 본문의 21%) |
| source_refs 있음 | 18/18 |
| speaker 있음 | 17/18 |

출처 연결은 멀쩡하다. 문제는 크기가 아니라 **claim만 읽었을 때 원문으로 돌아가야 한다는
사실조차 모른다**는 것이다. 예를 들어 `claim-20260825-011`은 31자다.

```
claim: 샌드박스 안에는 수명이 긴 자격증명을 절대 두지 않는다.
```

왜 그런지를 떠받치던 원문(브리지가 호스트 쪽에서 토큰을 붙이므로 토큰이 샌드박스 메모리에
들어가지 않는다)은 `claim-20260825-012`와 `-013`으로 갈라져 있고, 이 파일에는 그 연결이 없다.

## 고려한 대안과 기각 이유

**claim을 더 크게 쪼갠다.** 기각. 여러 문장을 한 claim에 담으면 일부만 참인 경우가 생겨
`verified`도 `rejected`도 줄 수 없다. 원자성은 상태를 줄 수 있게 하려고 있는 것이다.
`partially_true`가 있다는 사실 자체가 이 실패를 이미 겪었다는 뜻이다.

**frontmatter에 `quote` 키를 넣는다.** 기각. 인용은 길고 여러 줄이며 콜론과 따옴표가 섞인다.
frontmatter는 구조화된 메타데이터 자리다. 본문이 맞다.

## 결정

`create_claim`에 선택 인자 `quote`를 추가하고, 있으면 본문에 `## 원문` 절로 붙인다.

```markdown
## Claim

샌드박스 안에는 수명이 긴 자격증명을 절대 두지 않는다.

## 원문

> Credentials cannot live where the agent lives. Every guarantee the desktop
> gives you for free has to be rebuilt as an explicit system.
```

- 여러 줄 인용은 **모든 줄에 `> `를 붙인다.** 빈 줄에는 `>`만 붙여야 blockquote가 끊기지 않는다.
- `quote`를 안 주면 본문 모양은 예전 그대로다. 기존 claim 18개는 손대지 않는다.
- 스키마(`schema.py`)는 안 건드린다. frontmatter 키가 늘지 않는다.
- 인용이 원문에 실제로 있는지는 검증하지 않는다. 원문이 html에서 markdown으로 변환되며
  공백과 줄바꿈이 바뀌므로 문자열 대조가 거짓 실패를 낸다.

## 부수 효과: 검색이 좋아진다

`search.iter_docs`(search.py:108-116)가 `head + body`를 인덱싱한다. 지금은 body가 claim의
복사본이라 인덱싱할 게 없었다. `## 원문`이 들어가면 **원문 표현으로 검색해도 claim이 걸린다.**
claim은 한국어로 정리되고 원문은 영어인 경우가 많아서 실제로 차이가 크다.

## 상태 전이에서 살아남는가

살아남는다. `promote_claim`은 `meta, body = parse_doc(...)` 후 `render_doc(meta, body)`로
다시 쓴다(claims.py:88, 98). 본문은 건드리지 않는다. `set_claim_status`도 같은 경로다.

## 안 하는 것

- **기존 claim에 소급 적용하지 않는다.** claim 본문을 고치는 도구가 없고(`update_wiki_page`는
  `03_Resources` 하위로 제한된다), 만들면 게이트를 우회하는 경로가 하나 생긴다.
  원문이 vault에 살아 있으므로 필요하면 다시 ingest한다.
- **lint 검사를 추가하지 않는다.** `claim_without_quote`를 넣으면 기존 18개가 즉시 뜬다.
  info 등급이라 exit code에는 영향이 없지만, 첫 화면이 소음이 되는 값을 못 한다.
  나중에 quote 있는 claim이 다수가 되면 그때 넣는다.

## 검증

- `quote`를 주면 본문에 `## 원문`과 blockquote가 들어간다.
- 여러 줄 인용의 모든 줄에 `> `가 붙고, 빈 줄에도 `>`가 붙어 blockquote가 안 끊긴다.
- `quote`를 안 주면 본문이 예전과 글자 단위로 같다.
- `promote_claim`으로 상태를 바꿔도 `## 원문`이 남는다.
- MCP `tools/list`에서 `create_claim`의 `quote`가 선택 인자로 광고된다.
