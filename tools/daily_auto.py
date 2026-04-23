"""
매일 자동 뉴스 선별 & Discord 전송 (GitHub Actions 전용).

개선 사항:
- pubDate 파싱으로 당일/최근 기사 우선 선별 (시의성)
- og:image 실제 다운로드해서 크기·비율 검증 (세로 비율 + 고해상도 우선)
- 기사 본문 내 이미지도 스캔해 og:image보다 좋은 게 있으면 대체
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.discord_notify_ci import main as notify_main  # noqa: E402

# ── 설정 ────────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("https://www.news1.kr/rss/S1N5", "뉴스1"),
    ("https://rss.joins.com/joins_culture_list.xml", "중앙일보"),
    ("https://www.mk.co.kr/rss/40300002/", "매일경제"),
    ("https://design.co.kr/feed", "디자인프레스"),
    ("https://biz.heraldcorp.com/rss/0001016.xml", "헤럴드경제"),
]

ART_KEYWORDS = [
    "전시", "미술", "아트", "갤러리", "박물관", "예술", "작가",
    "비엔날레", "아트페어", "회고전", "특별전", "개관", "개막", "뮤지엄",
]

BLOCKED_DOMAINS = {
    "kh.or.kr", "korea.kr", "seoul.go.kr", "mmca.go.kr", "sema.seoul.go.kr",
    "cha.go.kr", "gov.kr",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# 이미지 품질 기준
MIN_WIDTH = 800          # 최소 가로 (px)
MIN_HEIGHT = 600         # 최소 세로 (px)
MIN_PORTRAIT_RATIO = 0.6 # height/width 최소 비율 (1.0=정사각, >1=세로)


# ── RSS 파싱 ─────────────────────────────────────────────────────────────────

def fetch_rss(url: str) -> list[dict]:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "xml")
    items = []
    for it in soup.find_all("item"):
        title_tag = it.find("title")
        link_tag = it.find("link")
        if not (title_tag and link_tag):
            continue
        pub = it.find("pubDate") or it.find("pubdate")
        items.append({
            "title": (title_tag.text or "").strip(),
            "url": (link_tag.text or "").strip(),
            "pub_raw": (pub.text or "").strip() if pub else "",
        })
    return items


def item_age_hours(item: dict) -> float:
    """기사 발행 후 경과 시간 (시간 단위). 날짜 없으면 999 반환."""
    raw = item.get("pub_raw", "")
    if not raw:
        return 999
    try:
        dt = parsedate_to_datetime(raw).astimezone(timezone.utc)
        age = datetime.now(timezone.utc) - dt
        return age.total_seconds() / 3600
    except Exception:
        return 999


def is_art_related(title: str) -> bool:
    return any(k in title for k in ART_KEYWORDS)


def is_blocked(url: str) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    return any(host == b or host.endswith("." + b) for b in BLOCKED_DOMAINS)


# ── 이미지 품질 검증 ──────────────────────────────────────────────────────────

def download_image(url: str) -> Image.Image | None:
    """이미지 URL을 다운로드해 PIL Image 반환. 실패 시 None."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return None
        ct = r.headers.get("content-type", "")
        if not ct.startswith("image/"):
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def image_score(w: int, h: int) -> float:
    """크기와 비율로 이미지 점수 계산. 높을수록 좋음.
    - 세로 비율 가중치: portrait일수록 우선
    - 해상도 가중치: 클수록 우선
    """
    ratio = h / max(w, 1)
    # 0.8(포스터 비율)에 가까울수록 높은 비율 점수
    ratio_score = min(ratio, 2.0) / 2.0
    size_score = min(w * h, 4_000_000) / 4_000_000
    return ratio_score * 0.6 + size_score * 0.4


def find_best_image(article_url: str) -> tuple[str, int, int] | tuple[None, None, None]:
    """기사에서 가장 좋은 이미지 URL과 크기 반환.

    1. og:image 시도
    2. twitter:image 시도
    3. 기사 본문 <img> 태그 스캔
    → 유효한 것들 중 image_score 가장 높은 것 반환
    Returns:
        (image_url, width, height) or (None, None, None)
    """
    try:
        r = requests.get(article_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [skip] 기사 fetch 실패: {e}", file=sys.stderr)
        return None, None, None

    # 후보 이미지 URL 수집
    candidates = []

    def _add(url: str):
        url = url.strip()
        if url and url.startswith("http"):
            candidates.append(url)

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        _add(og["content"])

    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        _add(tw["content"])

    # 기사 본문 img 태그 (넓이 200 이상 힌트 우선)
    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if not src:
            continue
        # 상대 경로 변환
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            parsed = urlparse(article_url)
            src = f"{parsed.scheme}://{parsed.netloc}{src}"
        if not src.startswith("http"):
            continue
        # 아이콘·로고 제외
        if any(x in src.lower() for x in ["logo", "icon", "btn", "badge", "avatar", "ad"]):
            continue
        w_hint = img.get("width", "")
        if w_hint and w_hint.isdigit() and int(w_hint) < 200:
            continue
        candidates.append(src)

    if not candidates:
        print("  [skip] 이미지 후보 없음", file=sys.stderr)
        return None, None, None

    # 중복 제거 (순서 유지)
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    # 각 후보 다운로드 & 점수 계산 (최대 5개)
    best_url, best_w, best_h, best_score = None, 0, 0, -1.0
    for url in unique[:5]:
        img_obj = download_image(url)
        if img_obj is None:
            continue
        w, h = img_obj.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            print(f"  [skip] 너무 작음 {w}x{h}: {url[:60]}", file=sys.stderr)
            continue
        ratio = h / w
        if ratio < MIN_PORTRAIT_RATIO:
            print(f"  [skip] 가로 비율 {ratio:.2f} (최소 {MIN_PORTRAIT_RATIO}): {url[:60]}", file=sys.stderr)
            continue
        score = image_score(w, h)
        print(f"  [후보] {w}x{h} ratio={ratio:.2f} score={score:.2f}: {url[:60]}", file=sys.stderr)
        if score > best_score:
            best_url, best_w, best_h, best_score = url, w, h, score

    if best_url:
        return best_url, best_w, best_h
    return None, None, None


# ── 후보 선별 ─────────────────────────────────────────────────────────────────

def pick_candidate(max_age_hours: float = 36.0):
    """RSS에서 시의성 + 이미지 품질 통과한 첫 후보 반환.

    max_age_hours 이내 기사 우선. 없으면 72h로 재시도.
    """
    for age_limit in [max_age_hours, 72.0]:
        print(f"\n[선별] 최대 {age_limit:.0f}시간 이내 기사 탐색", file=sys.stderr)
        result = _pick_from_feeds(age_limit)
        if result:
            return result
    print("[오류] 모든 RSS 소진, 후보 없음", file=sys.stderr)
    return None


def _pick_from_feeds(age_limit: float):
    for feed_url, source_name in RSS_FEEDS:
        print(f"\n[RSS] {source_name} {feed_url}", file=sys.stderr)
        try:
            items = fetch_rss(feed_url)
        except Exception as e:
            print(f"  [skip] fetch 실패: {e}", file=sys.stderr)
            continue

        # 아트 관련 + 블랙리스트 제외
        art_items = [
            it for it in items
            if is_art_related(it["title"]) and not is_blocked(it["url"])
        ]
        # 시의성 필터
        fresh_items = [it for it in art_items if item_age_hours(it) <= age_limit]

        # 최신 순 정렬
        fresh_items.sort(key=lambda x: item_age_hours(x))
        print(f"  전체={len(items)} 아트={len(art_items)} 최신={len(fresh_items)}건", file=sys.stderr)

        for item in fresh_items[:6]:
            age = item_age_hours(item)
            print(f"  [{age:.1f}h] {item['title'][:50]}", file=sys.stderr)
            img_url, w, h = find_best_image(item["url"])
            if img_url:
                print(f"  ✓ 채택: {w}x{h} {img_url[:60]}", file=sys.stderr)
                return {
                    "title": item["title"],
                    "url": item["url"],
                    "direct_image_url": img_url,  # 직접 이미지 URL (CI에서 재다운로드)
                    "source_name": source_name,
                    "age_hours": age,
                }

    return None


# ── 헤드라인 & 캡션 ──────────────────────────────────────────────────────────

def make_headlines(title: str) -> tuple[str, str]:
    """기사 제목에서 2줄 헤드라인 (각 줄 최대 11자)."""
    clean = re.sub(r"\[[^\]]+\]", "", title)
    clean = re.sub(r"\([^)]+\)", "", clean)
    clean = re.sub(r"[\"'''""]", "", clean)
    clean = clean.split("…")[0].split("·")[0].strip()
    clean = re.sub(r"\s+", " ", clean)

    words = clean.split()
    if not words:
        return "오늘의", "아트뉴스"
    if len(words) == 1:
        w = words[0]
        mid = max(1, len(w) // 2)
        return w[:mid][:11], (w[mid:][:11] or "소식")

    mid = max(1, len(words) // 2)
    line1 = "".join(words[:mid])[:11]
    line2 = "".join(words[mid:])[:11]
    return line1, (line2 or "소식")


def make_caption(title: str, source_name: str) -> str:
    return (
        f"{title.strip()}\n\n"
        f"#아트매거진 #문화예술 #전시추천 #현대미술 #{source_name}"
    )


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> int:
    picked = pick_candidate()
    if not picked:
        return 3

    h1, h2 = make_headlines(picked["title"])
    today = date.today().isoformat()

    meta = {
        "news_title": picked["title"],
        "news_url": picked["url"],
        "image_url": picked["direct_image_url"],  # 검증된 직접 이미지 URL
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

    age = picked.get("age_hours", 0)
    print(f"\n[완료] {picked['title']}", file=sys.stderr)
    print(f"       헤드라인: {h1} / {h2}", file=sys.stderr)
    print(f"       발행 경과: {age:.1f}시간", file=sys.stderr)
    print(f"       이미지: {picked['direct_image_url'][:80]}", file=sys.stderr)

    sys.argv = ["discord_notify_ci.py", meta_path]
    return notify_main()


if __name__ == "__main__":
    sys.exit(main())
