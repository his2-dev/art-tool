# v1_news_to_discord.json — JSON 복원 실패 (노드 목록만 회수)

전신 — 뉴스수집→요약→디스코드

원본이 중간부터 이중 이스케이프된 데다, 되돌리면 뒤쪽 `jsCode`의 정상 `\n` 이스케이프까지 함께 풀려 구조가 깨진다. v3가 상위 호환이라 노드 목록만 남긴다.

## 노드

1. When clicking 'Execute workflow'
2. Fetch News List
3. Extract News Blocks
4. Aggregate HTML
5. Parse News Data
6. OpenAI Chat Model
7. OpenAi-n8n-test
8. Structured Parser
9. Process News Array
10. Fetch Article Content
11. Summarize Article
12. Clean Summary Data
13. Collect All Summaries
14. Generate Discord Message
15. Send to Discord
16. Discord Bot account
17. Error Handler

원본: `~/Downloads/optimized_news_bot.json`
