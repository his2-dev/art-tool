"""
뉴스 기사 URL에서 메타데이터 추출 (og:title, og:image, og:site_name 등)
AI 없이 메타태그/캡션/본문 패턴을 조합해 기사 정보를 정리합니다.
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# curl_cffi: Chrome TLS 핑거프린트로 위장 → Cloudflare/JA3 기반 봇 차단 우회
# 일부 한국 뉴스 사이트(news1.kr, heraldcorp.com 등)는 Python requests의
# TLS 시그니처를 보고 403을 반환. curl_cffi가 있으면 우선 사용.
try:
    from curl_cffi import requests as _curl_requests  # type: ignore
    _HAS_CURL_CFFI = True
except ImportError:
    _curl_requests = None
    _HAS_CURL_CFFI = False


def _fetch_html(url: str, headers: dict, timeout: int = 15):
    """curl_cffi(Chrome 핑거프린트) 우선, requests fallback."""
    if _HAS_CURL_CFFI:
        try:
            r = _curl_requests.get(
                url, headers=headers, timeout=timeout,
                allow_redirects=True, impersonate="chrome120",
            )
            if r.status_code < 400:
                return r
        except Exception:
            pass
    return requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)


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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    resp = _fetch_html(url, headers, timeout=15)
    resp.raise_for_status()
    # 인코딩 자동 감지 보정 (한국 뉴스 사이트 대응)
    try:
        resp.encoding = resp.apparent_encoding
    except AttributeError:
        pass  # curl_cffi response may not have apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")

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
    image_url = _best_og_image(soup) or _get_best_image(soup)
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


def _best_og_image(soup: BeautifulSoup) -> str:
    """og:image:secure_url → og:image 순으로 반환. property/name 속성 모두 확인."""
    for prop in ["og:image:secure_url", "og:image"]:
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            return tag.get("content", "").strip()
        # 일부 사이트는 property 대신 name 속성 사용
        tag = soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return tag.get("content", "").strip()
    return ""


def _parse_srcset_largest(srcset: str) -> tuple:
    """srcset 문자열에서 가장 큰 너비의 (url, width) 반환."""
    best_url, best_w = "", 0
    for entry in srcset.split(","):
        parts = entry.strip().split()
        if not parts:
            continue
        url = parts[0]
        w = 0
        if len(parts) > 1:
            desc = parts[1]
            try:
                if desc.endswith("w"):
                    w = int(desc[:-1])
                elif desc.endswith("x"):
                    w = int(float(desc[:-1]) * 1000)
            except ValueError:
                pass
        if w > best_w:
            best_w, best_url = w, url
    return best_url, best_w


_IMG_SKIP = {"logo", "icon", "badge", "avatar", "btn", "spinner", "blank"}


def _get_best_image(soup: BeautifulSoup) -> str:
    """og:image가 없을 때 본문에서 가장 큰 이미지 URL 반환."""
    candidates: list[tuple[int, str]] = []

    # 1. twitter:image 메타태그 (높은 우선순위 가중치)
    for name in ("twitter:image", "twitter:image:src"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            candidates.append((99999, tag["content"].strip()))
            break

    # 2. 본문 img 태그 — srcset 우선, fallback src
    for img in soup.find_all("img"):
        srcset = img.get("data-srcset") or img.get("srcset", "")
        src = img.get("data-src") or img.get("src", "")

        # srcset에서 최대 너비 URL 추출
        if srcset:
            best_url, best_w = _parse_srcset_largest(srcset)
            if best_url and not any(s in best_url.lower() for s in _IMG_SKIP):
                candidates.append((best_w, best_url))

        if not src:
            continue
        if any(s in src.lower() for s in _IMG_SKIP):
            continue

        # width 속성으로 크기 추정
        raw_w = img.get("width") or img.get("data-width") or ""
        try:
            width = int(str(raw_w).rstrip("px")) if raw_w else 0
        except ValueError:
            width = 0

        if 0 < width < 200:
            continue

        candidates.append((width, src))

    if not candidates:
        return ""

    # 너비 내림차순 정렬 후 최대 크기 반환
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


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


def _suggest_headlines(title: str, description: str) -> tuple:
    """기사 제목 기반 2줄 헤드라인 초안 생성."""
    raw = title or description or ""
    text = raw.strip()
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([^)]+\)", " ", text)
    text = re.sub(r"[\"“”'’]", "", text)

    for sep in [" | ", "｜", "ㅣ"]:
        if sep in text:
            text = text.split(sep)[0]

    text = re.sub(r"\s+", " ", text).strip()

    quote_match = re.search(r"[\"“'‘]?([^\"”'’]{2,20})[\"”'’]?\s+(개막|개최|오픈|재개|공개|진행|개장|개편|운영|상영|전시|뜬다|연다)", title or "")
    if quote_match:
        quoted = re.sub(r"\s+", "", quote_match.group(1))
        action = re.sub(r"\s+", "", quote_match.group(2))
        prefix = (title or "").split(quote_match.group(1))[0]
        prefix_words = re.sub(r"[\"“”'’]", "", prefix).strip().split()
        place = prefix_words[-1] if prefix_words else ""
        line1 = _fit_headline(quoted)
        line2 = _fit_headline(f"{place}{action}")
    else:
        text = text.split("…")[0]
        words = [w for w in text.split() if w]
        if len(words) >= 2:
            line1 = _fit_headline("".join(words[: max(1, len(words) // 2)]))
            line2 = _fit_headline("".join(words[max(1, len(words) // 2) :]))
        else:
            compact = text.replace(" ", "")
            midpoint = max(1, min(len(compact) // 2, 9))
            line1 = _fit_headline(compact[:midpoint])
            line2 = _fit_headline(compact[midpoint:])

    if not line2:
        line2 = _fit_headline(description or "전시 소식")
    return line1, line2


def _fit_headline(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    compact = compact[:11]
    if len(compact) <= 9:
        return compact
    return compact[:9]
