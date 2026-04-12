"""
뉴스 기사 URL에서 메타데이터 추출 (og:title, og:image, og:site_name 등)
AI 불필요 — HTML 메타태그 파싱만 사용
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def parse_article(url: str) -> dict:
    """기사 URL에서 제목, 이미지, 출처를 추출합니다.

    Returns:
        {
            "title": str,        # 기사 제목
            "image_url": str,    # 대표 이미지 URL
            "source": str,       # 출처명 (예: 국립현대미술관)
            "site_name": str,    # 사이트명 (예: 연합뉴스)
            "description": str,  # 기사 요약
        }
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    # 인코딩 자동 감지 보정 (한국 뉴스 사이트 대응)
    resp.encoding = resp.apparent_encoding
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
    image_url = og("image") or _get_first_image(soup)
    site_name = og("site_name") or _domain_name(url)
    description = (
        og("description")
        or _meta_content(soup, "description")
        or ""
    )

    # 이미지 출처: 기사 본문에서 캡션 추출 시도
    image_credit = _find_image_credit(soup)
    source = image_credit or site_name

    return {
        "title": title,
        "image_url": image_url,
        "source": source,
        "site_name": site_name,
        "description": description,
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
                    cleaned = re.sub(r"^(사진|이미지|출처|자료|자료사진)\s*[=:·\s]*", "", text)
                    cleaned = re.sub(r"[ⓒ©]\s*", "", cleaned).strip()
                    if cleaned:
                        return cleaned
    return ""
