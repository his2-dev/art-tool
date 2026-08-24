"""
매일 자동 뉴스 선별 & Discord 전송 (GitHub Actions 전용 — Claude 스케줄 태스크의 폴백).

선별 파이프라인:
1. 후보 수집 — RSS(Bing News + 언론사) + 네이버뉴스 검색 크롤링. 죽은 소스는 자동 스킵
2. 큐레이션 점수 — 개막·회고전 등 뉴스성 키워드 가점, 인터뷰·칼럼·연재 감점/제외
3. 최근 30일 발행 이력과 URL·핵심 명사 겹침 검사 (중복 주제 방지)
4. 기사 내 이미지 실제 다운로드 검증 (해상도·세로 비율) 통과한 상위 3건 발행
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote, unquote, urlparse

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.article_parser import find_best_image, http_get, split_headline  # noqa: E402
from tools.textkit import topic_key  # noqa: E402

# ── 설정 ────────────────────────────────────────────────────────────────────


def _bing_news_rss(query: str) -> str:
    return f"https://www.bing.com/news/search?q={quote(query)}&format=rss&mkt=ko-KR"


# 검색 기반 피드를 앞에 둔다 — 클라우드 IP에서도 안정적으로 응답.
# 언론사 직접 RSS는 Actions IP에서 403/빈 응답이 잦아 보조용 (실패 시 자동 스킵).
RSS_FEEDS = [
    (_bing_news_rss("미술관 전시 개막"), "빙뉴스-전시"),
    (_bing_news_rss("갤러리 개인전 개막"), "빙뉴스-개인전"),
    (_bing_news_rss("아트페어 비엔날레"), "빙뉴스-아트페어"),
    (_bing_news_rss("회고전 특별전 미술"), "빙뉴스-회고전"),
    # 해외·랜드마크·거장 보강 — 국내 RSS가 잘 안 잡는 빅뉴스(거장 별세·랜드마크 완공 등)를
    # 한국어 보도로 받는다. 영문 RSS 대신 ko-KR 검색이라 헤드라인이 한국어로 유지됨.
    (_bing_news_rss("해외 미술관 전시 개막"), "빙뉴스-해외전시"),
    (_bing_news_rss("거장 화가 별세 회고전"), "빙뉴스-거장"),
    (_bing_news_rss("건축 완공 재개관 미술관"), "빙뉴스-건축"),
    (_bing_news_rss("세계 최초 미술관 랜드마크"), "빙뉴스-랜드마크"),
    # 문화 전 장르 — 미술 밖 소재가 수집 자체가 안 되던 문제 보완
    (_bing_news_rss("소설 영화화 드라마화 확정"), "빙뉴스-영상화"),
    (_bing_news_rss("웹툰 연재 시작 출판사 협업"), "빙뉴스-출판웹툰"),
    (_bing_news_rss("국가등록문화유산 등록 국보 보물 지정"), "빙뉴스-문화재"),
    (_bing_news_rss("도난 미술품 회수 환수 반환"), "빙뉴스-환수"),
    (_bing_news_rss("한국 최초 국제 수상 문화예술"), "빙뉴스-최초"),
    (_bing_news_rss("뮤지컬 브로드웨이 한국 배우 데뷔"), "빙뉴스-공연진출"),
    ("https://design.co.kr/feed", "디자인프레스"),
    ("https://www.yna.co.kr/rss/culture.xml", "연합뉴스"),
    ("https://www.khan.co.kr/rss/rssdata/culture_news.xml", "경향신문"),
    ("https://www.segye.com/Articles/RSSList/segye_culture.xml", "세계일보"),
    ("https://www.mk.co.kr/rss/30000023/", "매일경제"),
]

ART_KEYWORDS = [
    "전시", "미술", "아트", "갤러리", "박물관", "예술", "작가",
    "비엔날레", "아트페어", "회고전", "특별전", "개관", "개막", "뮤지엄",
    "조각", "회화", "사진전", "설치", "퍼포먼스", "드로잉",
    # 미술계 인물 표지어 — "OOO 화백/거장 별세" 류가 후보에 진입할 수 있게.
    "화가", "화백", "거장", "조각가", "건축가", "사진작가", "예술가", "아티스트",
]

# p.art_mag은 미술 전문지가 아니라 '문화 뉴스' 채널이다 (CLAUDE.md 편집 방향).
# 실제 수제 선정 이력(급류 영화화·민음사 콜라보·달러구트 디즈니·아이비 브로드웨이·
# 한글 의학교과서 등록·청년문화예술패스·산호 아이스너상)이 전부 미술 밖 장르라
# ART_KEYWORDS만으로는 게이트 진입조차 못 했다. 장르 축을 따로 연다.
CULTURE_KEYWORDS = [
    # 문학·출판·웹툰 ('작가'는 ART_KEYWORDS에 이미 있어 여기 넣지 않음 — is_art_related가
    # ART_KEYWORDS를 먼저 검사해 무조건 통과시키므로 EVENT_VERB 게이트가 적용될 일이 없다)
    "소설", "문학", "출판", "출판사", "시집", "에세이", "베스트셀러",
    "웹툰", "웹소설", "만화", "연재", "단행본", "번역서", "문학상",
    # 영상·공연 IP
    "영화화", "드라마화", "실사화", "애니화", "영화제", "제작 확정", "캐스팅",
    "뮤지컬", "브로드웨이", "웨스트엔드", "오페라", "발레", "국악", "연극",
    # 문화재·유산
    "문화재", "국가유산", "문화유산", "등록문화유산", "국보", "보물", "유물",
    "고궁", "종묘", "왕릉", "발굴", "환수", "반환",
    # 문화정책·기관
    "문화예술패스", "예술위원회", "문체부", "문화체육관광부", "국가유산청",
    # K팝·셀럽 × 문화
    "케이팝", "K팝", "아이돌", "그래미", "빌보드",
    # 브랜드·기관 콜라보 (민음사 콜라보 류) — EVENT_VERB 동반 조건이 노이즈를 막는다
    "콜라보", "굿즈", "팝업스토어", "에디션", "협업", "뮷즈",
    # 명화·미술품 사건 (르누아르 회수 류) — "미술" 글자가 없는 제목 대응
    "명화", "미술품", "걸작", "도난", "경매", "낙찰",
    # 애니·스튜디오 IP (겨울왕국3 류)
    "애니메이션", "디즈니", "픽사", "지브리", "속편", "시리즈 신작",
    # 궁궐·전통 의식 (경복궁 수문장 교대의식 류)
    "경복궁", "창덕궁", "덕수궁", "창경궁", "궁궐", "수문장", "무형유산", "전통의식",
]

# 장르 축이 열린 만큼, '사건'이 없는 단순 소개·상태 서술은 걸러야 한다.
# curation.md 하드 게이트 2번(사건 부재)의 코드판.
EVENT_VERB_RE = re.compile(
    r"확정|결정|발표|공개|개막|개관|출시|시작|재개|중단|철수|취소|무산|"
    r"수상|선정|위촉|임명|데뷔|초청|진출|입성|등록|지정|승격|"
    r"회수|환수|반환|발굴|복원|완공|준공|체결|협약|맞손|손잡|"
    r"돌파|경신|신기록|최초|보이콧|논란|고소|반발"
)
# 주의: '콜라보'는 EVENT_VERB_RE에 넣지 않는다 — CULTURE_KEYWORDS에도 '콜라보'가 있어
# 넣으면 두 조건을 같은 단어 하나가 동시에 만족시켜 '사건 동반' 게이트가 무력화된다.

# 건축·공간·랜드마크 — 단독 "건축"은 부동산 노이즈가 많아 ART_KEYWORDS에 넣지 않고,
# 트리거(건축/완공 등)와 문화 맥락(미술관/랜드마크 등)이 함께일 때만 통과시킨다.
ARCH_TRIGGER = ["건축", "완공", "준공", "재개관", "리뉴얼", "개장", "설계", "파빌리온", "랜드마크"]
ARCH_CULTURE = [
    "미술관", "박물관", "갤러리", "뮤지엄", "아트", "문화", "예술", "랜드마크",
    "건축가", "비엔날레", "파빌리온", "디자인", "대성당", "성당", "타워", "도서관", "공원",
    "사원", "수도원", "궁", "궁전", "왕궁", "고궁", "유적", "문화재",
]
# "완공/재개관/복원"은 랜드마크 '사건'이라 고유명사만 있는 제목(예: 사그라다 파밀리아 완공)도
# 통과시킨다. 단 토목·일반건물(도로·공장·병원 등)은 제외.
STRONG_ARCH = ["완공", "준공", "재개관", "복원", "개장"]
NONCULTURE_ARCH_RE = re.compile(r"도로|고속도로|교량|터널|철도|공항|항만|댐|발전소|공장|청사|병원|학교|터미널")
# 부동산·시공성 소식은 건축 트리거가 있어도 배제.
REALESTATE_RE = re.compile(r"아파트|분양|청약|오피스텔|재건축|재개발|입주|시공사|매매|부동산|단지|상가")

# 별세·부고 맥락 판별 — '거장'만 통과시킨다.
# 예술계 협회장·이사장 부고가 워낙 많아 예전엔 부고를 통째로 막았는데,
# 그 탓에 히가시노 게이고 같은 진짜 거장까지 놓쳤다. 그래서 2단으로 나눈다:
#   1단 FIGURE_RE  — '창작자인가' (미술 외 문학·영화·음악 직군까지)
#   2단 fame_tier() — '거장인가'  (위키백과 문서 규모, LLM 호출 없음)
DEATH_RE = re.compile(r"별세|타계|영면|선종|숙환|작고")
FIGURE_RE = re.compile(
    r"작가|화가|화백|거장|건축가|조각가|사진작가|예술가|디자이너|마에스트로|아티스트"
    r"|소설가|시인|극작가|만화가|삽화가"
    r"|감독|배우|작곡가|지휘자|피아니스트|무용가|안무가|성악가|명창")
# 조직 직함이 붙으면 인물이 아니라 '자리'가 주인공 → 위키 조회 없이 즉시 탈락.
OFFICE_RE = re.compile(
    r"협회장|이사장|관장|위원장|조합장|회장|총장|청장|국장|과장|교수|원장|대표이사|의원|시장|장관")

# 뉴스성 가점 키워드 (점수)
# 레퍼런스 채널(artart.today, b.framemag 등)이 다루는 콘텐츠 유형 반영:
# 대형 회고전·글로벌 아트씬·셀럽/팝컬처 접점·브랜드 콜라보에 가점
BOOST_KEYWORDS = {
    "개막": 5, "개관": 5, "회고전": 4, "특별전": 3, "기획전": 3,
    "비엔날레": 4, "아트페어": 4, "첫 공개": 3, "공개": 2, "수상": 3,
    "선정": 2, "미술관": 2, "뮤지엄": 2, "갤러리": 1, "개인전": 3,
    "신작": 2, "무료": 2, "오픈": 2, "유치": 2,
    "콜라보": 3, "팝업": 2, "협업": 2, "한정": 1,
    "해외": 1, "세계 최초": 3, "아시아 최초": 3, "국내 최초": 2,
    "리움": 2, "호암": 2, "국립현대미술관": 2, "아모레퍼시픽미술관": 2,
    # 건축·완공·랜드마크 (사그라다 파밀리아 완공 류)
    "완공": 4, "준공": 2, "재개관": 3, "리뉴얼": 2, "랜드마크": 3,
    "파빌리온": 2, "대성당": 2, "복원": 2,
    # 화제성 시그널 (국립현대 댄스플로어 변신 류) — "왜 재밌는지" 이야기가 되는 소식
    "변신": 3, "최초 공개": 3, "최초공개": 3, "첫 개방": 2, "철거": 2,
    "논란": 2, "신기록": 3, "이례적": 2, "파격": 3,
    # ── 문화 전 장르 사건 (실제 수제 선정 이력 반영) ──
    # 원작 IP 영상화·무대화 — 급류/달러구트 류. 우리 채널 최다 카테고리.
    "영화화": 6, "드라마화": 5, "실사화": 5, "애니화": 4, "제작 확정": 4,
    "브로드웨이": 5, "웨스트엔드": 4, "영화제": 3, "초청": 3, "데뷔": 3,
    # 출판·문학·웹툰
    "출판사": 2, "문학상": 3, "연재 시작": 3, "웹툰": 2, "번역 출간": 2,
    # 문화재·유산 — 한글 의학교과서 등록 류
    # "국가등록문화유산"은 "등록문화유산"의 상위 문자열이라 둘 다 두면 한 제목에서
    # +10으로 이중 가산된다. 더 구체적인 쪽 하나만 남긴다.
    "국가등록문화유산": 5, "국보": 4, "보물 지정": 4,
    "환수": 5, "반환": 3, "회수": 4, "발굴": 3,
    # 한국 최초·글로벌 진출 (가산점 신호)
    "한국 최초": 5, "한국인 최초": 5, "최초 수상": 4, "진출": 2, "입성": 3,
    # 논란·철수·보이콧
    "철수": 4, "보이콧": 4, "중단": 2, "무산": 2, "반발": 2,
    # 전국 단위 문화정책
    "문화예술패스": 4, "지원 확대": 2,
    # 사건 동사 일반
    "확정": 3, "결정": 2, "체결": 2, "맞손": 2,
}

# 감점 키워드 — 뉴스가 아닌 콘텐츠 유형
PENALTY_KEYWORDS = {
    "인터뷰": -8, "칼럼": -8, "기고": -8, "오피니언": -8, "사설": -8,
    # "별세"는 여기서 빼고 curation_score에서 맥락 판별(거장이면 가점, 아니면 감점).
    "멘토": -6, "연재": -6, "부고": -6, "단신": -4,
    "모집": -5, "공모": -4, "강좌": -6, "교육": -4, "체험": -3,
    "할인": -3, "이벤트 당첨": -5, "포토뉴스": -4, "동정": -6,
    # 상설·장기 진행 전시(퐁피두·키아프 류 evergreen) 감점 — 신선 트리거 가점으로 상쇄 가능.
    "상설": -5, "상시": -4, "연중": -4, "스테디": -3,
}

# 연재·인터뷰 마커 — 발견 시 즉시 제외
HARD_EXCLUDE_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫]|\[\s*(인터뷰|칼럼|기고|사설|오피니언|연재)|Q\s*&\s*A|\d+편\b")

# 예전엔 영화·드라마·뮤지컬을 '시각예술과 거리 멀다'며 통째로 막았는데, 그 탓에
# 급류 영화화·달러구트 디즈니·아이비 브로드웨이 같은 실제 선정감이 전부 탈락했다.
# 이제 장르로 막지 않고 '사건 없는 소비 정보'만 막는다.
OVEREXPOSED_KEYWORDS = [
    "박스오피스", "시청률", "예매율", "관객수", "흥행 순위", "재방송",
    "OTT 추천", "볼만한", "정주행", "결말 해석", "리뷰", "후기",
    "출연료", "열애", "결별", "복귀설", "루머",
]

BLOCKED_DOMAINS = {
    "kh.or.kr", "korea.kr", "seoul.go.kr", "mmca.go.kr", "sema.seoul.go.kr",
    "cha.go.kr", "gov.kr",
}

# 발행 기준
MIN_SCORE = 3.0          # 큐레이션 점수 하한
MIN_WIDTH = 800          # 이미지 최소 가로 (px)
MIN_HEIGHT = 600         # 이미지 최소 세로 (px)
MIN_PORTRAIT_RATIO = 0.6  # height/width 최소 비율


# ── RSS 파싱 ─────────────────────────────────────────────────────────────────

def _unwrap_redirect(url: str) -> str:
    """Bing News 등 리다이렉트 링크에서 원 기사 URL 추출."""
    host = urlparse(url).netloc.lower()
    if "bing.com" in host:
        qs = parse_qs(urlparse(url).query)
        if qs.get("url"):
            return unquote(qs["url"][0])
    return url


def fetch_rss(url: str) -> list:
    r = http_get(url, timeout=15)
    soup = BeautifulSoup(r.content, "xml")
    items = []
    for it in soup.find_all("item"):
        title_tag = it.find("title")
        link_tag = it.find("link")
        if not (title_tag and link_tag):
            continue
        link = _unwrap_redirect((link_tag.text or "").strip())
        pub = it.find("pubDate") or it.find("pubdate")
        items.append({
            "title": (title_tag.text or "").strip(),
            "url": link,
            "pub_raw": (pub.text or "").strip() if pub else "",
        })
    return items


# ── 네이버뉴스 검색 크롤링 (RSS 보강) ────────────────────────────────────────
# 레퍼런스 채널(아트인컬처·디자인프레스 등) 취향에 가까운 후보를 RSS가 못 잡을 때 보강.
# 인스타 채널 직접 크롤링은 로그인벽으로 비현실적 → 네이버뉴스 검색이 안정적 대안.
NAVER_QUERIES = [
    ("미술관 전시 개막", "네이버-전시"),
    ("갤러리 개인전 개막", "네이버-개인전"),
    ("거장 작가 별세 회고전", "네이버-거장"),
    ("미술관 재개관 건축 완공", "네이버-건축"),
    ("브랜드 아트 콜라보 팝업", "네이버-콜라보"),
    ("아이돌 배우 전시 미술", "네이버-셀럽"),
    ("소설 웹툰 영화화 드라마화 확정", "네이버-영상화"),
    ("국가등록문화유산 등록 국보 지정", "네이버-문화재"),
    ("한국 최초 국제상 수상 작가", "네이버-최초"),
    ("문화예술 지원사업 신청 시작", "네이버-정책"),
    ("박물관 미술관 논란 철수 회수", "네이버-이슈"),
]


def _naver_search_url(query: str) -> str:
    # where=news, sort=1(최신순). 기간 필터는 우리 age 로직에 맡김.
    return f"https://search.naver.com/search.naver?where=news&sort=1&query={quote(query)}"


def _parse_korean_age(text: str) -> float:
    """'3시간 전' / '2일 전' / '2026.06.13.' 같은 표기를 경과 시간(시간)으로."""
    m = re.search(r"(\d+)\s*분\s*전", text)
    if m:
        return int(m.group(1)) / 60
    m = re.search(r"(\d+)\s*시간\s*전", text)
    if m:
        return float(int(m.group(1)))
    m = re.search(r"(\d+)\s*일\s*전", text)
    if m:
        return int(m.group(1)) * 24.0
    m = re.search(r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})", text)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return max(0.0, (date.today() - d).days * 24.0)
        except ValueError:
            pass
    return 999.0


_NAVER_DATE_RE = re.compile(r"\d+\s*(?:분|시간|일)\s*전|20\d{2}\.\s*\d{1,2}\.\s*\d{1,2}")


def _naver_item_age(anchor) -> float:
    """뉴스 링크의 가장 가까운 조상 중 날짜 표기를 담은 블록을 찾아 경과 시간 반환.
    날짜를 못 찾으면 999(→ 신선도 필터에서 탈락)."""
    node = anchor
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = node.get_text(" ", strip=True)
        if len(text) > 600:  # 블록이 커지면 다른 기사까지 섞임 → 중단
            break
        if _NAVER_DATE_RE.search(text):
            return _parse_korean_age(text)
    return 999.0


def _is_naver_internal(host: str) -> bool:
    return host.endswith("naver.com") or host.endswith("naver.me")


def fetch_naver_news(query: str) -> list:
    """네이버뉴스 검색결과 페이지를 curl_cffi로 받아 (제목·원문URL·경과시간) 추출.
    구 레이아웃(a.news_tit)을 우선 쓰되, 신 레이아웃(해시 클래스 sds-comps)에서는
    '외부 기사 링크 + 헤드라인 길이/한글' 휴리스틱으로 제목 앵커를 잡는다."""
    r = http_get(_naver_search_url(query), timeout=15)
    soup = BeautifulSoup(r.content, "html.parser")
    items, seen = [], set()

    # 1) 구 레이아웃
    for a in soup.select("a.news_tit"):
        title = (a.get("title") or a.get_text() or "").strip()
        link = (a.get("href") or "").strip()
        if title and link.startswith("http") and link not in seen:
            seen.add(link)
            items.append({"title": title, "url": link, "pub_raw": "", "age_pre": _naver_item_age(a)})
    if items:
        return items

    # 2) 신 레이아웃 — 해시 클래스에 의존하지 않는 텍스트 휴리스틱
    for a in soup.find_all("a"):
        link = (a.get("href") or "").strip()
        if not link.startswith("http"):
            continue
        if _is_naver_internal(urlparse(link).netloc.lower()):
            continue  # 언론사 홈·네이버뉴스 미러 링크 제외 (원문 기사 앵커만)
        title = a.get_text(" ", strip=True)
        if len(title) < 12 or not re.search(r"[가-힣]", title):
            continue  # 썸네일·언론사명 등 비제목 앵커 제거
        if link in seen:
            continue
        seen.add(link)
        items.append({"title": title, "url": link, "pub_raw": "", "age_pre": _naver_item_age(a)})
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
    # 부동산·시공 소식은 어떤 키워드가 있어도 제외.
    if REALESTATE_RE.search(title):
        return False
    # 미술계 인물 별세 — "거장/화가 별세"는 미술 키워드가 약해도 통과.
    if DEATH_RE.search(title) and FIGURE_RE.search(title):
        return True
    # 사건 없는 소비 정보(박스오피스·시청률·연예 가십)는 장르 불문 제외.
    if any(k in title for k in OVEREXPOSED_KEYWORDS):
        return False
    if any(k in title for k in ART_KEYWORDS):
        return True
    # 문화 전 장르(문학·영상 IP·문화재·정책·K팝) — 단, '사건 동사'가 있을 때만.
    # 장르어만 있고 사건이 없으면 단순 소개글이라 우리 채널 소재가 아니다.
    if any(k in title for k in CULTURE_KEYWORDS) and EVENT_VERB_RE.search(title):
        return True
    # 건축·공간·랜드마크 — 문화 맥락이 함께일 때만 (단독 "건축"은 통과 안 됨).
    if any(k in title for k in ARCH_TRIGGER):
        if any(k in title for k in ARCH_CULTURE):
            return True
        # 완공·재개관·복원 등 랜드마크 사건은 문화 맥락어가 없어도 통과 (토목·일반건물 제외).
        if any(k in title for k in STRONG_ARCH) and not NONCULTURE_ARCH_RE.search(title):
            return True
    return False


# ── L1 시그널 가점 ──────────────────────────────────────────────────────────
# signal_scan.py가 레퍼런스 채널에서 잡아둔 '지금 반응 있는 소재'와 겹치는 기사에 가점.
#
# 단 레퍼런스 채널을 그대로 따라가면 안 된다 — 그쪽은 최신 소식 말고도 역사·상식·명작
# 해설 같은 에버그린을 자체 발굴해 올린다. 우리는 실시간 뉴스라 그건 겹치면 안 됨.
# 그래서 두 겹으로 막는다:
#   ① signal_scan이 에버그린으로 분류한 신호는 여기서 제외
#   ② 가점은 '오늘 수집된 기사'와 토큰이 겹칠 때만 → 기사가 없는 소재는 애초에 못 받음
SIGNAL_BONUS_MAX = 10.0
KST = timezone(timedelta(hours=9))
_signals_cache = None


def load_signals():
    """오늘(없으면 어제) 시그널을 읽어 시의성 있는 것만 토픽 집합으로 반환."""
    global _signals_cache
    if _signals_cache is not None:
        return _signals_cache

    _signals_cache = []
    # signals_latest.json(커밋됨)이 우선 — 클라우드 스케줄은 이것만 볼 수 있다.
    # 로컬 전체 스냅샷(output/signals/*.json)은 gitignore 대상이라 로컬에서만 존재한다.
    sig_dir = os.path.join(ROOT, "output", "signals")
    paths = [os.path.join(ROOT, "output", "signals_latest.json")]
    paths += [os.path.join(sig_dir, f"{(datetime.now(KST) - timedelta(days=d)):%Y-%m-%d}.json")
              for d in (0, 1)]

    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        # 너무 오래된 시그널은 시의성이 없다 (실시간 뉴스 매거진이므로)
        scanned = str(data.get("scanned_at", ""))[:10]
        if scanned:
            try:
                age = (datetime.now(KST).date()
                       - datetime.strptime(scanned, "%Y-%m-%d").date()).days
                if age > 2:
                    continue
            except ValueError:
                pass
        for s in data.get("signals", []):
            if s.get("evergreen"):
                continue                       # ① 에버그린 제외
            topic = set(s.get("topic") or [])
            if len(topic) >= 2:
                _signals_cache.append((topic, float(s.get("score", 0)), s.get("caption", "")))
        if _signals_cache:
            break
    return _signals_cache


def signal_bonus(title: str) -> float:
    """기사 제목이 시그널 토픽과 겹치면 가점. 겹치는 신호가 없으면 0.

    토크나이저는 signal_scan과 반드시 같은 것을 써야 한다 — 다르면 토큰이 어긋나
    가점이 조용히 0으로 수렴한다.
    """
    signals = load_signals()
    if not signals:
        return 0.0
    tokens = topic_key(title)
    if not tokens:
        return 0.0

    best = 0.0
    for topic, score, _cap in signals:
        overlap = len(tokens & topic)
        if overlap >= 2:                       # ② 실제 기사와 겹칠 때만
            best = max(best, min(SIGNAL_BONUS_MAX, 4 + overlap + score / 5))
    return best


# ── 부고 명성 판정 ──────────────────────────────────────────────────────────
# 한국어 위키백과 공개 API만 사용한다 (인증·요금 없음, LLM 호출 0).
# 부고 제목일 때만 호출되므로 하루 1~4회 수준.
WIKI_API = "https://ko.wikipedia.org/w/api.php"
FAME_LANG_MIN, FAME_BYTES_MIN = 15, 25000     # 거장
FAME_LANG_EDGE, FAME_BYTES_EDGE = 8, 15000    # 경계
_PERSON_HINT = ("소설가", "미술가", "화가", "작가", "감독", "배우", "시인", "조각가",
                "사진작가", "건축가", "디자이너", "작곡가", "지휘자", "무용가", "만화가",
                "음악가", "예술가", "가수", "연출가", "설치미술", "피아니스트", "성악가")
_wiki_cache: dict = {}


def _wiki_page(name: str):
    """위키 문서 요약. 실패하면 None (네트워크 문제로 파이프라인이 죽지 않게)."""
    if name in _wiki_cache:
        return _wiki_cache[name]
    out = None
    try:
        r = http_get(
            f"{WIKI_API}?action=query&titles={quote(name)}"
            "&prop=langlinks|description|info&lllimit=500&format=json&redirects=1",
            timeout=10)
        for pid, p in r.json().get("query", {}).get("pages", {}).items():
            if pid == "-1":
                break
            desc = p.get("description", "") or ""
            out = {"title": p.get("title", ""), "langs": len(p.get("langlinks", [])),
                   "bytes": p.get("length", 0),
                   "person": any(h in desc for h in _PERSON_HINT)}
    except Exception:
        out = None
    _wiki_cache[name] = out
    return out


def _wiki_search(name: str, hint: str):
    """동음이의 대응 — '김창열'은 가수 문서로 가버려서 '김창열 (화가)'를 못 찾는다."""
    key = f"s:{name}:{hint}"
    if key in _wiki_cache:
        return _wiki_cache[key]
    out = None
    try:
        r = http_get(f"{WIKI_API}?action=query&list=search"
                     f"&srsearch={quote(name + ' ' + hint)}&srlimit=3&format=json",
                     timeout=10)
        for hit in r.json().get("query", {}).get("search", []):
            info = _wiki_page(hit["title"])
            if info and info["person"] and \
                    name.replace(" ", "") in info["title"].replace(" ", ""):
                out = info
                break
    except Exception:
        out = None
    _wiki_cache[key] = out
    return out


def _name_candidates(title: str):
    """부고 제목에서 인물명 후보 추출.
    한국어 부고는 대개 '<수식어> <직군> <이름> 별세' 꼴."""
    t = re.sub(r"[\[\]<>《》「」'\"…·]", " ", title)
    toks = re.sub(r"\s+", " ", DEATH_RE.split(t)[0]).strip().split()
    for i, w in enumerate(toks):
        if FIGURE_RE.search(w):
            if i + 1 < len(toks):
                yield re.sub(r"(씨|님|옹|여사|선생)$", "",
                             " ".join(toks[i + 1:i + 3])).strip()  # 외국인 2어절
                yield toks[i + 1]
            if i > 0:
                yield toks[i - 1]
    for w in sorted((w for w in toks if re.fullmatch(r"[가-힣]{2,6}", w)
                     and not FIGURE_RE.search(w) and not OFFICE_RE.search(w)),
                    key=len, reverse=True)[:1]:
        yield w


def obit_score(title: str) -> float:
    """부고 제목 → 큐레이션 가감점. 거장 +7 / 경계 +2 / 그 외 -8."""
    if OFFICE_RE.search(title):
        return -8.0
    m = FIGURE_RE.search(title)
    if not m:
        return -8.0

    cands = [c for c in _name_candidates(title) if c and len(c) >= 2]
    best = None
    for c in cands:
        info = _wiki_page(c)
        if info and info["person"] and (best is None or info["langs"] > best["langs"]):
            best = info
    if best is None:
        for c in cands[:2]:
            best = _wiki_search(c, m.group(0))
            if best:
                break
    if best is None:
        return -8.0
    if best["langs"] >= FAME_LANG_MIN or best["bytes"] >= FAME_BYTES_MIN:
        return 7.0
    if best["langs"] >= FAME_LANG_EDGE or best["bytes"] >= FAME_BYTES_EDGE:
        return 2.0
    return -8.0


def curation_score(title: str, age_hours: float) -> float:
    """뉴스성·시의성 기반 큐레이션 점수. 높을수록 좋음. 음수면 부적합."""
    if HARD_EXCLUDE_RE.search(title):
        return -100.0
    score = 0.0
    for kw, pts in BOOST_KEYWORDS.items():
        if kw in title:
            score += pts
    for kw, pts in PENALTY_KEYWORDS.items():
        if kw in title:
            score += pts
    # 별세·부고 맥락: 거장이면 최상위 화제(가점), 협회장·무명이면 강한 감점.
    if DEATH_RE.search(title):
        score += obit_score(title)
    # L1 시그널 — 레퍼런스 채널에서 지금 반응 있는 소재와 겹치면 최우선 가점.
    score += signal_bonus(title)
    # 시의성: 24시간 이내 +3 → 72시간에서 0으로 선형 감소
    score += max(0.0, (72 - min(age_hours, 72)) / 72 * 3)
    return score


# ── 발행 이력 (중복 방지) ──────────────────────────────────────────────────────

def _bad_news_url(url: str) -> bool:
    """Discord 링크로 못 쓸 URL — 빈 값 또는 미해제 Bing 추적 링크."""
    if not url:
        return True
    host = urlparse(url).netloc.lower()
    return host.endswith("bing.com") or host == "bing.com"


def _git(args: list) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def _add_branch_history(published_urls: set, noun_sets: list, days: int) -> None:
    """프라이머리(claude/* 브랜치)가 최근 발행한 큐레이션도 이력에 합친다.
    폴백이 프라이머리와 같은 주제를 다시 내는 것을 막는다. git 불가 환경이면 조용히 패스."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin",
                        "+refs/heads/claude/*:refs/remotes/origin/claude/*"],
                       capture_output=True, timeout=60)
        branches = [b.strip() for b in _git(
            ["for-each-ref", "--sort=-committerdate",
             "--format=%(refname:short)", "refs/remotes/origin/claude/"]).splitlines() if b.strip()]
    except Exception:
        return
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    for ref in branches[:40]:
        for f in _git(["-c", "core.quotepath=false", "ls-tree", "-r",
                       "--name-only", ref, "output/news"]).splitlines():
            if not f.endswith(".json") or "_auto" in f:
                continue
            try:
                meta = json.loads(_git(["show", f"{ref}:{f}"]))
            except Exception:
                continue
            if str(meta.get("published_at", "2000-01-01"))[:10] < cutoff:
                continue
            if meta.get("news_url"):
                published_urls.add(meta["news_url"])
            sig = topic_signature(
                f"{meta.get('news_title','')} {meta.get('headline1','')} {meta.get('headline2','')}")
            if sig[0] or sig[1]:
                noun_sets.append(sig)


def load_recent_published(days: int = 30):
    """최근 N일 발행 JSON에서 (URL 집합, 제목 핵심명사 집합 리스트) 반환.
    main의 폴백 발행분 + 프라이머리(claude/*)의 큐레이션 발행분을 모두 포함한다."""
    published_urls = set()
    noun_sets = []
    output_dir = os.path.join(ROOT, "output", "news")
    if not os.path.isdir(output_dir):
        return published_urls, noun_sets
    cutoff = date.today() - timedelta(days=days)
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json"):
            continue
        try:
            file_date = date.fromisoformat(fname[:10])
            if file_date < cutoff:
                continue
        except ValueError:
            continue
        try:
            with open(os.path.join(output_dir, fname), encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        if meta.get("news_url"):
            published_urls.add(meta["news_url"])
        for cand in meta.get("candidates", []):
            if cand.get("url"):
                published_urls.add(cand["url"])
        sig = topic_signature(
            f"{meta.get('news_title', '')} {meta.get('headline1', '')} {meta.get('headline2', '')}"
        )
        if sig[0] or sig[1]:
            noun_sets.append(sig)
    _add_branch_history(published_urls, noun_sets, days)
    return published_urls, noun_sets


_NOUN_STOP = {
    "전시", "개막", "개관", "공개", "특별전", "기획전", "미술관", "갤러리",
    "박물관", "예술", "미술", "작가", "아트", "서울", "한국", "오늘", "이번",
}

# 일반 미술·기사 상용어 — 고유명이 아니라서, 이 토큰만 겹친다고 '같은 기사'로
# 보면 안 된다(서로 다른 비엔날레·서로 다른 회고전 등). 주제어 판정에서 제외.
_GENERIC_TERMS = {
    "현대미술", "비엔날레", "회고전", "특별전", "기획전", "아트페어", "미술관",
    "박물관", "갤러리", "퍼포먼스", "설치미술", "개인전", "사진전", "프로젝트",
    "페스티벌", "컬렉션", "디자인", "건축", "작품전", "인산인해", "전시회",
    "오프닝", "도슨트", "큐레이터", "미디어아트", "아티스트", "프리뷰",
}


def extract_key_nouns(title: str) -> set:
    """제목에서 일반 핵심명사 추출 (3자 이상 연속 한글/영문 단어, 불용어 제외)."""
    words = re.findall(r"[가-힣A-Za-z]{3,}", title)
    return {w for w in words if w not in _NOUN_STOP}


def extract_subjects(title: str) -> set:
    """식별성 높은 '주제어'(인물명·기관명 등 고유명) 추출 — 일반 상용어는 제외.
    '호크니'처럼 한 기사를 특정하는 토큰. 하나만 겹쳐도 같은 사건으로 본다."""
    return {w for w in extract_key_nouns(title) if w not in _GENERIC_TERMS}


def topic_signature(title: str) -> tuple:
    """중복 판정용 (일반명사 집합, 주제어 집합)."""
    return (extract_key_nouns(title), extract_subjects(title))


def is_dup_topic(title: str, signatures: list) -> bool:
    """이미 채택/발행된 항목과 같은 주제인지.
    - 일반 핵심명사가 2개 이상 겹치거나,
    - 고유 주제어(인물·기관명)가 1개라도 겹치면 중복."""
    nouns, subjects = topic_signature(title)
    for prior_nouns, prior_subjects in signatures:
        if len(nouns & prior_nouns) >= 2:
            return True
        if subjects & prior_subjects:
            return True
    return False


def is_blocked(url: str) -> bool:
    host = re.sub(r"^www\.", "", urlparse(url).netloc.lower())
    return any(host == b or host.endswith("." + b) for b in BLOCKED_DOMAINS)


# ── 후보 선별 ─────────────────────────────────────────────────────────────────

def pick_candidates(n: int = 2, max_age_hours: float = 36.0) -> list:
    """점수 상위 + 이미지 검증 통과한 후보 n개 반환. 부족하면 72h로 완화."""
    skip_urls, noun_sets = load_recent_published(days=30)
    print(f"[중복제외] 최근 30일 발행 {len(noun_sets)}건 로드", file=sys.stderr)

    for age_limit in [max_age_hours, 72.0]:
        print(f"\n[선별] 최대 {age_limit:.0f}시간 이내 기사 탐색", file=sys.stderr)
        results = _pick_from_feeds(age_limit, skip_urls, noun_sets, max_pick=n)
        if results:
            return results
    print("[오류] 모든 RSS 소진, 후보 없음", file=sys.stderr)
    return []


def _collect_fresh(items, source_name, age_limit, skip_urls, seen_urls, all_fresh) -> int:
    """후보 항목들을 필터·채점해 통과분을 all_fresh에 추가. 통과 건수 반환."""
    kept = 0
    for it in items:
        if it["url"] in seen_urls or it["url"] in skip_urls:
            continue
        if not is_art_related(it["title"]) or is_blocked(it["url"]) or _bad_news_url(it["url"]):
            continue
        # 네이버 크롤링 항목은 age를 미리 계산해 둠(age_pre), RSS는 pubDate로 계산.
        age = it["age_pre"] if it.get("age_pre") is not None else item_age_hours(it)
        if age > age_limit:
            continue
        score = curation_score(it["title"], age)
        if score < MIN_SCORE:
            continue
        seen_urls.add(it["url"])
        it["_source"] = source_name
        it["_score"] = score
        it["_age"] = age
        all_fresh.append(it)
        kept += 1
    return kept


def _pick_from_feeds(age_limit: float, skip_urls: set, noun_sets: list, max_pick: int = 3) -> list:
    all_fresh = []
    seen_urls = set()
    for feed_url, source_name in RSS_FEEDS:
        print(f"\n[RSS] {source_name} {feed_url[:80]}", file=sys.stderr)
        try:
            items = fetch_rss(feed_url)
        except Exception as e:
            print(f"  [skip] fetch 실패: {e}", file=sys.stderr)
            continue
        kept = _collect_fresh(items, source_name, age_limit, skip_urls, seen_urls, all_fresh)
        print(f"  전체={len(items)} 통과={kept}건", file=sys.stderr)

    # 네이버뉴스 검색 크롤링 — 레퍼런스 채널 취향에 가까운 후보 보강.
    for query, source_name in NAVER_QUERIES:
        print(f"\n[네이버] {source_name} '{query}'", file=sys.stderr)
        try:
            items = fetch_naver_news(query)
        except Exception as e:
            print(f"  [skip] fetch 실패: {e}", file=sys.stderr)
            continue
        kept = _collect_fresh(items, source_name, age_limit, skip_urls, seen_urls, all_fresh)
        print(f"  전체={len(items)} 통과={kept}건", file=sys.stderr)

    if not all_fresh:
        return []

    # 큐레이션 점수 내림차순 (동점이면 최신순)
    all_fresh.sort(key=lambda x: (-x["_score"], x["_age"]))

    results = []
    session_nouns = list(noun_sets)  # 발행 이력 + 이번 세션 채택분
    scan_limit = max(20, max_pick * 7)
    for item in all_fresh[:scan_limit]:
        if is_dup_topic(item["title"], session_nouns):
            print(f"  [중복주제] {item['title'][:50]}", file=sys.stderr)
            continue
        print(
            f"  [score={item['_score']:.1f} {item['_age']:.1f}h] {item['title'][:50]} ({item['_source']})",
            file=sys.stderr,
        )
        img_url, w, h = find_best_image(
            item["url"],
            min_width=MIN_WIDTH,
            min_height=MIN_HEIGHT,
            min_ratio=MIN_PORTRAIT_RATIO,
        )
        if not img_url:
            continue
        print(f"  ✓ 채택 {len(results)+1}/{max_pick}: {w}x{h} {img_url[:70]}", file=sys.stderr)
        results.append({
            "title": item["title"],
            "url": item["url"],
            "direct_image_url": img_url,
            "source_name": _publisher_name(item["url"], item["_source"]),
            "age_hours": item["_age"],
        })
        session_nouns.append(topic_signature(item["title"]))
        if len(results) >= max_pick:
            break

    return results


def _publisher_name(article_url: str, feed_name: str) -> str:
    """출처 표기용 이름. 검색 피드면 기사 도메인, 언론사 피드면 피드명."""
    if feed_name.startswith("빙뉴스"):
        host = urlparse(article_url).netloc
        return re.sub(r"^www\.", "", host)
    return feed_name


# ── 헤드라인 & 캡션 ──────────────────────────────────────────────────────────

def make_headlines(title: str) -> tuple:
    """기사 제목에서 자연스러운 2줄 헤드라인 (어절 경계 분할, 각 줄 최대 11자)."""
    line1, line2 = split_headline(title)
    if not line1:
        line1 = "오늘의"
    if not line2:
        line2 = "아트 뉴스"
    return line1, line2


def make_caption(title: str, source_name: str) -> str:
    clean = re.sub(r"\[[^\]]*\]", "", title).strip()
    clean = re.sub(r"\s+", " ", clean)
    return (
        f"{clean}\n\n"
        f"#문화예술 #전시추천 #현대미술 #전시소식 #아트매거진"
    )


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> int:
    from tools.discord_sender import send_news_to_discord
    from tools.news_poster import generate_news_poster

    candidates = pick_candidates(n=2)
    if not candidates:
        print("[오류] 후보 없음 — Discord 전송 생략", file=sys.stderr)
        return 3

    today = date.today().isoformat()
    os.makedirs("output/news", exist_ok=True)

    all_titles = [{"title": c["title"], "url": c["url"]} for c in candidates]
    success_count = 0

    for i, picked in enumerate(candidates, 1):
        h1, h2 = make_headlines(picked["title"])
        source_str = f"© {picked['source_name']}"
        caption = make_caption(picked["title"], picked["source_name"])

        meta = {
            "news_title": picked["title"],
            "news_url": picked["url"],
            "image_url": picked["direct_image_url"],
            "headline1": h1,
            "headline2": h2,
            "source": source_str,
            "caption": caption,
            "published_at": today,
            "candidates": all_titles,
        }

        meta_path = f"output/news/{today}_auto_{i}.json"
        image_path = f"output/news/{today}_auto_{i}.png"

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        try:
            generate_news_poster(
                headline1=h1,
                headline2=h2,
                source=source_str,
                image_url=picked["direct_image_url"] or None,
                output_path=image_path,
                scale=2,
            )
        except Exception as e:
            print(f"[경고] 이미지 생성 실패 ({i}), 다크 배경 재시도: {e}", file=sys.stderr)
            generate_news_poster(
                headline1=h1,
                headline2=h2,
                source=source_str,
                image_url=None,
                output_path=image_path,
                scale=2,
            )

        age = picked.get("age_hours", 0)
        print(f"\n[발행 {i}/{len(candidates)}] {picked['title']}", file=sys.stderr)
        print(f"       헤드라인: {h1} / {h2}", file=sys.stderr)
        print(f"       경과: {age:.1f}시간 | 이미지: {image_path}", file=sys.stderr)

        status = send_news_to_discord(
            image_path=image_path,
            news_title=picked["title"],
            news_url=picked["url"],
            headline1=h1,
            headline2=h2,
            source=source_str,
            caption=caption,
            candidates=all_titles,
        )
        if status == 200:
            success_count += 1

    print(f"\n[요약] {success_count}/{len(candidates)}개 Discord 전송 완료", file=sys.stderr)
    return 0 if success_count > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
