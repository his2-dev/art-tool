"""
매일 자동 뉴스 선별 & Discord 전송 (GitHub Actions 전용).

동작:
1. 화이트리스트 RSS 피드에서 최신 아트/문화 기사 수집
2. 각 후보에 대해 og:image 존재 + 다운로드 가능 여부 검증
3. 검증 통과한 첫 후보로 메타 JSON 생성 + discord_notify_ci 호출

회색 이미지(og:image 누락/차단) 방지를 위해:
- 정부/공공기관 도메인(kh.or.kr, korea.kr 등)은 블랙리스트
- og:image URL을 HEAD 요청으로 실제 접근 가능한지 확인
- 실패 시 다음 후보로 스킵
"""

import json
import os
import re
import sys
from datetime import date
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.article_parser import parse_article  # noqa: E402
from tools.discord_notify_ci import main as notify_main  # noqa: E402

# 아트/문화 RSS 피드 (순서대로 시도)
RSS_FEEDS = [
    ("https://www.news1.kr/rss/S1N5", "뉴스1"),
    ("https://rss.joins.com/joins_culture_list.xml", "중앙일보"),
    ("https://www.mk.co.kr/rss/40300002/", "매일경제 문화"),
    ("https://design.co.kr/feed", "디자인프레스"),
]

# 선별 키워드 (하나라도 매칭되면 후보)
ART_KEYWORDS = [
    "전시", "미술", "아트", "갤러리", "박물관", "예술", "작가",
    "비엔날레", "아트페어", "회고전", "특별전", "개관", "개막",
]

# 제외 도메인 (og:image 차단 or 품질 낮음)
BLOCKED_DOMAINS = {
    "kh.or.kr", "korea.kr", "seoul.go.kr", "mmca.go.kr", "sema.seoul.go.kr",
    "cha.go.kr", "gov.kr",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def fetch_rss(url: str):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "xml")
    items = []
    for it in soup.find_all("item"):
        title_tag = it.find("title")
        link_tag = it.find("link")
        if not (title_tag and link_tag):
            continue
        items.append({
            "title": (title_tag.text or "").strip(),
            "url": (link_tag.text or "").strip(),
        })
    return items


def is_art_related(title: str) -> bool:
    return any(k in title for k in ART_KEYWORDS)


def is_blocked(url: str) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    return any(host == b or host.endswith("." + b) for b in BLOCKED_DOMAINS)


def verify_og_image(article_url: str) -> str:
    """기사 URL에서 og:image를 추출하고 실제 다운로드 가능한지 검증.

    Returns:
        사용 가능한 이미지 URL (검증 실패 시 빈 문자열)
    """
    try:
        meta = parse_article(article_url)
    except Exception as e:
        print(f"  [skip] parse 실패: {e}", file=sys.stderr)
        return ""

    image_url = meta.get("image_url", "")
    if not image_url:
        print("  [skip] og:image 없음", file=sys.stderr)
        return ""

    # 실제 접근 가능한지 HEAD 요청
    try:
        r = requests.head(image_url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            print(f"  [skip] image HEAD {r.status_code}: {image_url[:80]}", file=sys.stderr)
            return ""
        ct = r.headers.get("content-type", "")
        if not ct.startswith("image/"):
            print(f"  [skip] not image (ct={ct}): {image_url[:80]}", file=sys.stderr)
            return ""
    except Exception as e:
        print(f"  [skip] image HEAD 실패: {e}", file=sys.stderr)
        return ""

    return image_url


def pick_candidate():
    """RSS 피드에서 검증 통과한 첫 후보 반환."""
    for feed_url, source_name in RSS_FEEDS:
        print(f"[RSS] {feed_url}", file=sys.stderr)
        try:
            items = fetch_rss(feed_url)
        except Exception as e:
            print(f"  [skip] fetch 실패: {e}", file=sys.stderr)
            continue

        art_items = [it for it in items if is_art_related(it["title"]) and not is_blocked(it["url"])]
        print(f"  후보 {len(art_items)}건", file=sys.stderr)

        for item in art_items[:8]:
            print(f"  검증 시도: {item['title'][:50]}", file=sys.stderr)
            image_url = verify_og_image(item["url"])
            if image_url:
                return {
                    "title": item["title"],
                    "url": item["url"],
                    "image_url": item["url"],  # CI가 og:image 재추출
                    "source_name": source_name,
                }

    return None


def make_headlines(title: str):
    """기사 제목에서 2줄 헤드라인 (각 줄 최대 11자)."""
    clean = re.sub(r"\[[^\]]+\]", "", title)
    clean = re.sub(r"\([^)]+\)", "", clean)
    clean = re.sub(r"[\"'''""]", "", clean)
    clean = clean.split("…")[0].strip()
    clean = re.sub(r"\s+", " ", clean)

    words = clean.split()
    if not words:
        return "오늘의", "아트뉴스"

    if len(words) == 1:
        w = words[0]
        mid = max(1, len(w) // 2)
        return w[:mid][:11], w[mid:][:11] or "소식"

    mid = max(1, len(words) // 2)
    line1 = "".join(words[:mid])[:11]
    line2 = "".join(words[mid:])[:11]
    return line1, line2 or "소식"


def make_caption(title: str, source_name: str) -> str:
    return (
        f"{title.strip()}\n\n"
        f"#아트매거진 #문화예술 #전시추천 #현대미술 #{source_name}"
    )


def main():
    picked = pick_candidate()
    if not picked:
        print("[오류] 검증 통과한 후보 없음", file=sys.stderr)
        return 3

    h1, h2 = make_headlines(picked["title"])
    today = date.today().isoformat()
    meta = {
        "news_title": picked["title"],
        "news_url": picked["url"],
        "image_url": picked["url"],
        "headline1": h1,
        "headline2": h2,
        "source": f"© {picked['source_name']}",
        "caption": make_caption(picked["title"], picked["source_name"]),
        "candidates": [{"title": picked["title"], "url": picked["url"]}],
    }

    meta_path = f"output/news/{today}_auto.json"
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[자동 선별] {picked['title']}", file=sys.stderr)
    print(f"[헤드라인] {h1} / {h2}", file=sys.stderr)
    print(f"[메타] {meta_path}", file=sys.stderr)

    sys.argv = ["discord_notify_ci.py", meta_path]
    return notify_main()


if __name__ == "__main__":
    sys.exit(main())
