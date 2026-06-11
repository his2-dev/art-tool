"""
뉴스 기사 URL에서 메타데이터 추출 (og:title, og:image, og:site_name 등)
AI 없이 메타태그/캡션/본문 패턴을 조합해 기사 정보를 정리합니다.
"""

import re
import sys
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def http_get(url: str, timeout: int = 15):
    """GET 요청. curl_cffi가 설치돼 있으면 Chrome TLS 핑거프린트로 우회 시도 후,
    실패하면 일반 requests로 폴백. 한국 뉴스 사이트의 봇 차단(403) 대응용."""
    try:
        from curl_cffi import requests as cf_requests
        r = cf_requests.get(
            url,
            impersonate="chrome120",
            timeout=timeout,
            allow_redirects=True,
            headers={"Accept-Language": DEFAULT_HEADERS["Accept-Language"]},
        )
        if r.status_code == 200:
            return r
    except ImportError:
        pass
    except Exception:
        pass
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def parse_article(url: str) -> dict:
    """기사 URL에서 제목, 이미지, 출처를 추출합니다.

    Returns:
        {
            "title": str,        # 기사 제목
            "image_url": str,    # 대표 이미지 URL
            "source": str,       # 출처명 (예: 국립현대미술관)
            "site_name": str,    # 사이트명 (예: 연합뉴스)
            "description": str,  # 기사 요약
            "suggested_headline1": str,  # 추천 헤드라인 1줄
            "suggested_headline2": str,  # 추천 헤드라인 2줄
        }
    """
    resp = http_get(url, timeout=15)
    # bytes로 넘겨 BeautifulSoup이 meta charset 기반 인코딩 자동 감지 (한국 뉴스 사이트 대응)
    soup = BeautifulSoup(resp.content, "html.parser")

    def og(prop: str) -> str:
        tag = soup.find("meta", property=f"og:{prop}")
        if tag:
            return tag.get("content", "").strip()
        # fallback: name 속성
        tag = soup.find("meta", attrs={"name": f"og:{prop}"})
        if tag:
            return tag.get("content", "").strip()
        return ""

    title = og("title") or _get_title(soup)
    image_url = og("image") or _get_first_image(soup)
    site_name = og("site_name") or _domain_name(url)
    description = (
        og("description")
        or _meta_content(soup, "description")
        or ""
    )

    # 이미지 출처: 기사 본문/캡션/메타에서 최대한 원출처 추출
    image_credit = _find_image_credit(soup)
    source = image_credit or site_name
    suggested_headline1, suggested_headline2 = _suggest_headlines(title, description)

    return {
        "title": title,
        "image_url": image_url,
        "source": source,
        "site_name": site_name,
        "description": description,
        "suggested_headline1": suggested_headline1,
        "suggested_headline2": suggested_headline2,
    }


def _get_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else ""


def _meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name})
    if tag:
        return tag.get("content", "").strip()
    return ""


def _domain_name(url: str) -> str:
    """URL에서 도메인 이름 추출 (예: news.naver.com → 네이버 뉴스)."""
    domain = urlparse(url).netloc
    # www. 제거
    domain = re.sub(r"^www\.", "", domain)
    return domain


def _get_first_image(soup: BeautifulSoup) -> str:
    """og:image가 없을 때 본문 첫 번째 큰 이미지 추출."""
    # twitter:image 시도
    tag = soup.find("meta", attrs={"name": "twitter:image"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    # 본문 img 태그
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        # 작은 아이콘 제외
        w = img.get("width", "")
        if w and w.isdigit() and int(w) < 200:
            continue
        if any(skip in src.lower() for skip in ["logo", "icon", "badge", "avatar", "btn"]):
            continue
        return src
    return ""


def _find_image_credit(soup: BeautifulSoup) -> str:
    """기사 본문에서 이미지 캡션/크레딧 추출 시도."""
    # 일반적인 이미지 캡션 클래스/태그
    caption_selectors = [
        "figcaption",
        ".image_caption",
        ".img_caption",
        ".photo_caption",
        ".caption",
        "[class*='caption']",
        "[class*='credit']",
        ".source",
    ]
    for sel in caption_selectors:
        tags = soup.select(sel)
        for tag in tags:
            text = tag.get_text(strip=True)
            if text and len(text) < 100:
                # "제공", "사진", "촬영", "©" 등이 있으면 출처일 가능성 높음
                if any(kw in text for kw in ["제공", "사진", "촬영", "©", "ⓒ", "출처"]):
                    # 정리: "사진=국립현대미술관" → "국립현대미술관"
                    cleaned = _clean_credit_text(text)
                    if cleaned:
                        return cleaned

    full_text = soup.get_text(" ", strip=True)
    patterns = [
        r"\[([^\[\]]{1,30}) 제공",
        r"\(([^\(\)]{1,30}) 제공",
        r"\[([^\[\]]{1,40} 제공)\]",
        r"\(([^\(\)]{1,40} 제공)\)",
        r"(?:사진|이미지|자료사진|출처)\s*[=:·]\s*([^\s\|\]\[<>{}]{1,40})",
        r"([가-힣A-Za-z0-9·\-\s]{1,30})\s+제공",
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text)
        if match:
            cleaned = _clean_credit_text(match.group(1))
            if cleaned:
                return cleaned
    return ""


def _clean_credit_text(text: str) -> str:
    cleaned = text.strip()
    if "[" in cleaned:
        cleaned = cleaned.split("[")[-1]
    if "(" in cleaned and len(cleaned.split("(")[-1]) <= 30:
        cleaned = cleaned.split("(")[-1]
    cleaned = re.sub(r"^(사진|이미지|출처|자료|자료사진)\s*[=:·\s]*", "", cleaned)
    cleaned = re.sub(r"\s*(사진|이미지|자료사진)$", "", cleaned)
    cleaned = re.sub(r"\s*제공.*$", "", cleaned)
    cleaned = re.sub(r"\s*재판매.*$", "", cleaned)
    cleaned = re.sub(r"\s*DB 금지.*$", "", cleaned)
    cleaned = re.sub(r"^\[|\]$", "", cleaned)
    cleaned = re.sub(r"^\(|\)$", "", cleaned)
    cleaned = re.sub(r"[ⓒ©]\s*", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


# 헤드라인 2줄 분할 — 사실형 서술어 (이 단어가 들어간 어절을 2줄 끝에 배치)
_ACTION_WORDS = [
    "개막", "개최", "개관", "공개", "오픈", "재개", "개장", "폐막",
    "선정", "수상", "유치", "출범", "공개돼", "열린다", "열려", "연다",
]
_HEADLINE_MAX = 11


def _suggest_headlines(title: str, description: str) -> tuple:
    """기사 제목 기반 2줄 헤드라인 초안 생성 (자연스러운 한국어 우선)."""
    line1, line2 = split_headline(title or description or "")
    if not line2:
        line2 = split_headline(description or "전시 소식")[0] or "전시 소식"
    return line1, line2


def split_headline(title: str, max_len: int = _HEADLINE_MAX) -> tuple:
    """기사 제목을 2줄 헤드라인으로 분할.

    원칙:
    - 단어(어절) 중간 절단 금지 — 공백 경계에서만 자름
    - 가능하면 1줄=기관·전시명(명사), 2줄=`~ 개막` 등 사실형 서술
    - 따옴표 인용 티저("부산의 봄...")보다 사실 절을 우선 채택
    """
    text = (title or "").strip()
    text = re.sub(r"\[[^\]]*\]", " ", text)          # [단독], [포토] 등 제거
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[\"“”'‘’《》〈〉<>]", "", text)   # 따옴표·괄호류 제거 (내용은 유지)
    text = re.sub(r"\s+", " ", text).strip()

    # 절 분리: "…", "ㅣ", "|", "—" 등. 사실형 서술어가 포함된 절을 우선 채택
    clauses = [c.strip() for c in re.split(r"…|\.\.\.|[|｜ㅣ]|—|–| - ", text) if c.strip()]
    if not clauses:
        return "오늘의", "아트 뉴스"
    chosen = next(
        (c for c in clauses if any(a in c for a in _ACTION_WORDS)),
        max(clauses, key=len),
    )

    words = chosen.split()
    if len(words) == 1:
        return _fit_words(words, max_len), ""

    # 사실형 서술어가 든 어절을 찾아 그 어절이 2줄의 끝이 되도록 분할
    action_idx = next(
        (i for i in range(len(words) - 1, -1, -1)
         if any(a in words[i] for a in _ACTION_WORDS)),
        None,
    )
    if action_idx is not None and action_idx > 0:
        line2_words = words[action_idx:action_idx + 1]
        # 2줄 앞쪽으로 어절을 최대한 붙임 (1줄에 최소 1어절은 남김)
        j = action_idx - 1
        while j >= 1:
            w = words[j]
            # 연도·숫자 토큰("1956-1976" 등)은 2줄이 너무 짧을 때만 건너뛰고 계속 확장
            if re.fullmatch(r"[\d\-~.·]+", w):
                if len(" ".join(line2_words)) < 4:
                    j -= 1
                    continue
                break
            if _join_len(line2_words, w) > max_len:
                break
            line2_words.insert(0, w)
            j -= 1
        line1 = _fit_words(words[: j + 1], max_len)
        line2 = " ".join(line2_words)
        if len(line2) > max_len:
            line2 = _fit_words(line2_words, max_len)
        line1 = _prefer_org_word(line1, line2, text, max_len)
        return _polish_line(line1), _polish_line(line2)

    # 서술어가 없으면 글자 수 기준 절반에서 어절 경계로 분할
    total = len(" ".join(words))
    line1_words, acc = [], 0
    for i, w in enumerate(words):
        if line1_words and (acc + 1 + len(w) > max_len or acc >= total // 2):
            return (
                _polish_line(_fit_words(line1_words, max_len)),
                _polish_line(_fit_words(words[i:], max_len)),
            )
        line1_words.append(w)
        acc += len(w) + (1 if acc else 0)
    return _polish_line(_fit_words(line1_words, max_len)), ""


def _join_len(words: list, extra: str) -> int:
    return len(" ".join([extra] + words))


_ORG_SUFFIXES = ("미술관", "박물관", "갤러리", "뮤지엄", "아트센터", "미술제", "비엔날레", "아트페어", "문화원")
_ORG_SUFFIX_RE = re.compile("|".join(_ORG_SUFFIXES))


def _prefer_org_word(line1: str, line2: str, full_text: str, max_len: int) -> str:
    """1줄에 기관명이 없는데 제목 다른 절에 고유 기관명이 있으면 1줄을 기관명으로 교체.
    예: '리움미술관, ... 개막' → 1줄 '리움미술관'

    고유명 조건: '리움미술관'처럼 접미사로 끝나는 합성어만 인정.
    단독 '뮤지엄'이나 조사 붙은 '갤러리서'는 제외."""
    if _ORG_SUFFIX_RE.search(line1) or _ORG_SUFFIX_RE.search(line2):
        return line1
    for w in full_text.split():
        cleaned = w.strip(",.·")
        for suffix in _ORG_SUFFIXES:
            if (
                cleaned.endswith(suffix)
                and len(cleaned) > len(suffix)
                and len(cleaned) <= max_len
            ):
                return cleaned
    return line1


def _polish_line(line: str) -> str:
    return line.strip(" ,.·—–-")


def _fit_words(words: list, max_len: int) -> str:
    """어절 단위로 max_len 이내까지만 이어 붙임. 첫 어절이 초과하면 그 어절만 절단."""
    out, acc = [], 0
    for w in words:
        add = len(w) + (1 if out else 0)
        if acc + add > max_len:
            break
        out.append(w)
        acc += add
    if not out and words:
        return words[0][:max_len]
    return " ".join(out)


# ── 기사 내 최적 이미지 선택 ──────────────────────────────────────────────────

def find_best_image(
    article_url: str,
    min_width: int = 600,
    min_height: int = 450,
    min_ratio: float = 0.0,
    max_candidates: int = 6,
):
    """기사에서 가장 좋은 이미지 URL과 크기 반환.

    og:image → twitter:image → 본문 <img> 순으로 후보를 모은 뒤
    실제 다운로드해 해상도·비율을 검증하고 점수가 가장 높은 것을 채택.
    og:image가 저해상도 썸네일인 경우 본문 원본 이미지로 대체된다.

    Returns:
        (image_url, width, height) 또는 (None, None, None)
    """
    try:
        resp = http_get(article_url, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception as e:
        print(f"  [skip] 기사 fetch 실패: {e}", file=sys.stderr)
        return None, None, None

    candidates = []

    def _add(u: str):
        u = (u or "").strip()
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            p = urlparse(article_url)
            u = f"{p.scheme}://{p.netloc}{u}"
        if u.startswith("http") and u not in candidates:
            candidates.append(u)

    og = soup.find("meta", property="og:image")
    if og:
        _add(og.get("content", ""))
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw:
        _add(tw.get("content", ""))
    for img in soup.find_all("img", src=True):
        src = img.get("src", "")
        if any(x in src.lower() for x in ["logo", "icon", "btn", "badge", "avatar", "/ad/", "banner"]):
            continue
        w_hint = img.get("width", "")
        if w_hint and w_hint.isdigit() and int(w_hint) < 300:
            continue
        _add(src)

    best_url, best_w, best_h, best_score = None, 0, 0, -1.0
    for u in candidates[:max_candidates]:
        img_obj = _download_pil_image(u)
        if img_obj is None:
            continue
        w, h = img_obj.size
        if w < min_width or h < min_height:
            print(f"  [skip] 너무 작음 {w}x{h}: {u[:70]}", file=sys.stderr)
            continue
        ratio = h / w
        if ratio < min_ratio:
            print(f"  [skip] 가로 비율 {ratio:.2f} (최소 {min_ratio}): {u[:70]}", file=sys.stderr)
            continue
        score = _image_score(w, h)
        print(f"  [후보] {w}x{h} ratio={ratio:.2f} score={score:.2f}: {u[:70]}", file=sys.stderr)
        if score > best_score:
            best_url, best_w, best_h, best_score = u, w, h, score

    if best_url:
        return best_url, best_w, best_h
    return None, None, None


def _download_pil_image(url: str):
    try:
        from io import BytesIO
        from PIL import Image
        r = http_get(url, timeout=20)
        ct = r.headers.get("content-type", "")
        if ct and not ct.startswith("image/"):
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def _image_score(w: int, h: int) -> float:
    """세로 비율(포스터 친화)과 해상도가 높을수록 높은 점수."""
    ratio = h / max(w, 1)
    ratio_score = min(ratio, 2.0) / 2.0
    size_score = min(w * h, 4_000_000) / 4_000_000
    return ratio_score * 0.5 + size_score * 0.5
