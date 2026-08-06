"""L1 시그널 스캔 — 레퍼런스 채널이 '오늘 뭘 올렸나'를 수집해 화제를 먼저 잡는다.

기존 파이프라인(daily_auto.py)은 기사 RSS에서 시작해 화제성을 '추측'한다.
이 스크립트는 순서를 뒤집는다 — 이미 반응이 검증된 게시물을 먼저 찾고,
그 토픽으로 기사를 역검색하게 한다.

⚠️ 로컬 전용. GitHub Actions에 절대 연결하지 말 것.
   비공식 공개 엔드포인트를 CI에서 매일 때리면 IP가 차단되고,
   같은 IP를 쓰는 daily_auto.py의 이미지 수집까지 함께 막힌다.

사용법:
    python tools/signal_scan.py              # 수집 + 리포트
    python tools/signal_scan.py --report     # 재수집 없이 최신 스냅샷만 리포트
    python tools/signal_scan.py --no-youtube # 인스타/스레드만 (빠름)

출력:
    output/signals/YYYY-MM-DD.json   당일 스냅샷
    output/signals/history.sqlite    누적 이력 (전일 대비 급상승 계산용)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.textkit import topic_key  # noqa: E402

try:
    from curl_cffi import requests as rq
except ImportError:  # pragma: no cover
    sys.exit("curl_cffi 필요: pip install curl_cffi")

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output" / "signals"
DB_PATH = OUT_DIR / "history.sqlite"

IG_APP_ID = "936619743392459"

# ── 레퍼런스 채널 ─────────────────────────────────────────────────────────
# tier: 화제 감지력. hi=대형(신규 감지만), mid=중형(급상승 추적 가능)
# 12개 상한 때문에 발행이 잦은 대형 계정은 하루만 지나도 밀려난다 →
# 급상승(delta) 추적은 mid 계정에서만 의미가 있다.
IG_CHANNELS = [
    ("artart.today", "hi"),      # 861K, 최상위 화제 감지기
    ("eyesmag", "hi"),           # 1.35M, 팝컬처×아트
    ("wkorea", "hi"),            # 5.1M, 셀럽·패션×아트
    ("lingrongdang", "hi"),      # 187K, 주간 큐레이션
    ("odoc.mag", "hi"),          # 123K, 예술→라이프스타일
    ("b.framemag", "mid"),       # 42K, 직접 경쟁
    ("aroundmagazine", "mid"),   # 36K, 인터뷰·에세이
    ("bplatform", "mid"),        # 24K, 아트북·독립출판
    ("vostok_mag", "mid"),       # 15K, 사진예술
]

THREADS_CHANNELS = ["artart.today", "b.framemag"]

YOUTUBE_QUERIES = [
    "전시 미술관", "아트페어 갤러리", "작가 인터뷰 작업실",
    "브랜드 아트 콜라보", "미술 논란 이슈", "박물관 특별전",
]

# 대형 계정(wkorea·eyesmag)은 화장품·패션 광고를 대량 올린다 → 문화예술 신호가 묻힌다.
# 주의: 아이돌 화보 캡션에 '아티스트'·'작품'이 흔해서 ART_RE에 걸려 통과해버린다
#       (실측: '#광고 정국 샤넬 향수'가 31점으로 1위를 먹었음) → 명시적 광고는 무조건 컷.
HARD_AD_RE = re.compile(r"#광고|앰배서더|앰버서더|글로벌 앰|협찬|유료 광고")
AD_RE = re.compile(r"AD\b|캠페인 화보|신제품|할인|증정 이벤트|구매|출시 기념|런칭|프로모션")
# 아이돌·뷰티·패션 맥락 — 진짜 미술 키워드가 함께 없으면 우리 소재가 아니다.
POPIDOL_RE = re.compile(r"향수|화장품|스킨케어|컬렉션 런칭|플래그십|뷰티|메이크업|립|파운데이션"
                        r"|앨범|컴백|타이틀곡|팬미팅|월드투어|화보 촬영")
STRONG_ART_RE = re.compile(r"전시|미술관|박물관|갤러리|비엔날레|아트페어|개인전|기획전|회고전"
                           r"|작가|화가|조각|설치미술|공예|도록|큐레이|아트북|건축")
ART_RE = re.compile(
    r"전시|미술관|박물관|갤러리|비엔날레|아트페어|작가|화가|조각|설치미술|드로잉|공예"
    r"|건축|디자인|타이포|사진전|개인전|기획전|회고전|작품|예술|아티스트|큐레이|도록"
    r"|미술|아트|공연|연극|오페라|발레|무용|클래식|국악|문학|소설|시집|출판")

# 피아트는 '실시간 뉴스' 매거진이다. 레퍼런스 채널은 최신 소식 말고도
# 역사·상식·명작 해설 같은 에버그린을 자체 발굴해 올리는데, 그건 우리가 겹치면 안 된다.
# → 에버그린 신호는 감점하고, 최종 가점은 '최신 기사가 실제로 존재하는' 신호에만 준다.
EVERGREEN_RE = re.compile(
    r"\d{3,4}년\s*(에|,|\s)|세기|시대|당시|유래|기원|역사 속|알고 보면|알고보니"
    r"|다시 보는|재조명|명작|걸작|상식|이야기 모음|모아봤|소개합니다|아시나요|하곤 한다"
    r"|미술사|~하던|추천 \d|BEST|베스트|모음|정리해")
TIMELY_RE = re.compile(
    r"개막|개최|공개|발표|출시|런칭|오픈|수상|선정|별세|타계|최초|신작|신간|첫 "
    r"|오늘|이번 주|이번주|내일|모레|D-\d|예정|확정|논란|화제|근황|재결합|컴백"
    r"|\d{1,2}월 \d{1,2}일|2026")


# ── 저장소 ────────────────────────────────────────────────────────────────
def db_connect() -> sqlite3.Connection:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS post (
            platform TEXT, channel TEXT, post_id TEXT,
            taken_at TEXT, caption TEXT, url TEXT,
            first_seen TEXT,
            PRIMARY KEY (platform, post_id)
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS metric (
            platform TEXT, post_id TEXT, seen_at TEXT,
            likes INTEGER, comments INTEGER, views INTEGER,
            PRIMARY KEY (platform, post_id, seen_at)
        )""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            seen_at TEXT, platform TEXT, channel TEXT, ok INTEGER, note TEXT
        )""")
    con.commit()
    return con


def record(con, now, platform, channel, items):
    """수집 결과를 이력 DB에 적재."""
    for it in items:
        con.execute(
            "INSERT OR IGNORE INTO post VALUES (?,?,?,?,?,?,?)",
            (platform, channel, it["id"], it.get("taken_at", ""),
             it.get("caption", "")[:400], it.get("url", ""), now))
        con.execute(
            "INSERT OR REPLACE INTO metric VALUES (?,?,?,?,?,?)",
            (platform, it["id"], now, it.get("likes"), it.get("comments"),
             it.get("views")))
    con.commit()


# ── 수집기 ────────────────────────────────────────────────────────────────
def new_session():
    s = rq.Session(impersonate="chrome")
    try:
        s.get("https://www.instagram.com/",
              headers={"Referer": "https://www.google.com/"}, timeout=20)
    except Exception:
        pass
    return s


def fetch_instagram(s, username):
    """web_profile_info — 비로그인으로 최근 12개 + 좋아요/댓글까지 나온다."""
    r = s.get(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers={"x-ig-app-id": IG_APP_ID, "Referer": "https://www.instagram.com/"},
        timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    user = (r.json().get("data") or {}).get("user")
    if not user:
        raise RuntimeError("user 없음 (비공개/차단)")

    items = []
    for edge in user["edge_owner_to_timeline_media"]["edges"]:
        n = edge["node"]
        cap = n.get("edge_media_to_caption", {}).get("edges") or []
        items.append({
            "id": n["shortcode"],
            "url": f"https://www.instagram.com/p/{n['shortcode']}/",
            "taken_at": datetime.fromtimestamp(n["taken_at_timestamp"], KST).isoformat(),
            "likes": (n.get("edge_liked_by") or n.get("edge_media_preview_like") or {}).get("count"),
            "comments": (n.get("edge_media_to_comment") or {}).get("count"),
            "views": n.get("video_play_count") or n.get("video_view_count"),
            "is_video": n.get("is_video", False),
            "caption": (cap[0]["node"]["text"] if cap else "").replace("\n", " "),
        })
    return items, user["edge_followed_by"]["count"]


def fetch_threads(s, username):
    """스레드 공개 프로필 HTML에서 게시물 텍스트/좋아요 추출.

    비로그인 HTML에는 4건 안팎만 실린다 (인스타 12건보다 적음) → 보조 신호로만.
    """
    r = s.get(f"https://www.threads.com/@{username}",
              headers={"Referer": "https://www.google.com/"}, timeout=25)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    h = r.text
    dec = json.JSONDecoder()

    items = []
    for m in re.finditer(r'"caption":\{', h):
        try:
            obj, _ = dec.raw_decode(h[m.end() - 1:])
        except Exception:
            continue
        text = (obj.get("text") or "").replace("\n", " ")
        if len(text) < 15:
            continue
        tail = h[m.end():m.end() + 4000]
        like = re.search(r'"like_count":(\d+)', tail)
        pid = obj.get("pk") or str(abs(hash(text)))
        items.append({
            "id": f"th_{pid}",
            "caption": text,
            "likes": int(like.group(1)) if like else None,
            "url": f"https://www.threads.com/@{username}",
        })
    if not items:
        raise RuntimeError("게시물 파싱 0건 (구조 변경 의심)")
    return items


def fetch_youtube(query, days=7, limit=8):
    """yt-dlp로 날짜순 검색. 최근 업로드 중 조회수 높은 것 = 화제."""
    # sp=CAISBAgCEAE : 업로드 날짜순 + 이번 주
    url = ("https://www.youtube.com/results?search_query="
           + rq.utils.quote(query) + "&sp=CAISBAgCEAE%3D")
    cp = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--playlist-end", str(limit), "-J", url],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    if cp.returncode != 0 or not cp.stdout:
        raise RuntimeError((cp.stderr or "yt-dlp 실패")[:120])
    entries = json.loads(cp.stdout).get("entries") or []
    return [{
        "id": f"yt_{e.get('id')}",
        "caption": e.get("title") or "",
        "url": f"https://youtu.be/{e.get('id')}",
        "views": e.get("view_count"),
        "channel_name": e.get("channel") or "",
    } for e in entries if e.get("id")]


# ── 분석 ──────────────────────────────────────────────────────────────────
# 토크나이저는 daily_auto.py와 공유한다 (tools/textkit.py) — 갈라지면 가점이 0으로 수렴.


def analyse(con, now, snapshot):
    """신규 감지 + 급상승 + 교차검증."""
    yesterday = (datetime.fromisoformat(now) - timedelta(days=2)).isoformat()

    known = {r[0] for r in con.execute(
        "SELECT post_id FROM post WHERE first_seen < ?", (now,))}

    signals = []
    for platform, channel, items in snapshot:
        for it in items:
            is_new = it["id"] not in known

            # 급상승: 같은 게시물의 과거 좋아요 대비 증가율
            prev = con.execute(
                "SELECT likes FROM metric WHERE post_id=? AND seen_at<? "
                "ORDER BY seen_at DESC LIMIT 1", (it["id"], now)).fetchone()
            delta = None
            if prev and prev[0] and it.get("likes"):
                delta = it["likes"] - prev[0]

            if not is_new and not (delta and delta > 0):
                continue

            cap = it.get("caption", "")
            if HARD_AD_RE.search(cap):
                continue  # 명시적 광고·앰배서더는 예술 키워드가 있어도 무조건 제외

            is_art = bool(ART_RE.search(cap))
            strong_art = bool(STRONG_ART_RE.search(cap))
            if POPIDOL_RE.search(cap) and not strong_art:
                continue  # 아이돌·뷰티 소식은 진짜 미술 맥락이 있을 때만

            is_ad = bool(AD_RE.search(cap))
            if is_ad and not is_art:
                continue  # 순수 커머스도 제외

            score = 0.0
            if is_new:
                score += 3
            if delta:
                score += min(delta / 10, 8)
            if it.get("views"):
                score += min(it["views"] / 1000, 6)
            if it.get("likes"):
                score += min(it["likes"] / 100, 5)
            if strong_art:
                score += 8      # 전시·작가 등 확실한 미술 소재
            elif is_art:
                score += 3      # '아티스트·작품' 정도의 약한 신호
            else:
                score -= 10
            if is_ad:
                score -= 4

            # 시의성 — 우리는 실시간 뉴스라 에버그린(역사·상식·명작해설)은 겹치면 안 된다
            evergreen = bool(EVERGREEN_RE.search(cap)) and not TIMELY_RE.search(cap)
            if evergreen:
                score -= 12

            signals.append({
                "platform": platform, "channel": channel,
                "id": it["id"], "url": it.get("url", ""),
                "caption": it.get("caption", "")[:150],
                "likes": it.get("likes"), "views": it.get("views"),
                "delta": delta, "is_new": is_new,
                "evergreen": evergreen,
                "score": round(score, 1),
                "topic": topic_key(cap),
            })

    # 교차검증 — 서로 다른 채널이 같은 고유명사를 다루면 강한 신호
    for a in signals:
        hits = {b["channel"] for b in signals
                if b["channel"] != a["channel"] and len(a["topic"] & b["topic"]) >= 2}
        if hits:
            a["cross"] = len(hits)
            a["score"] += 5 * min(len(hits), 3)

    # topic은 daily_auto.py가 기사 매칭에 쓰므로 JSON에 남긴다 (set → list)
    for a in signals:
        a["topic"] = sorted(a["topic"])

    signals.sort(key=lambda x: -x["score"])
    return signals


# ── 리포트 ────────────────────────────────────────────────────────────────
def print_report(signals, failures, top=12):
    print(f"\n{'=' * 74}\n📡 L1 시그널 — 상위 {top}건\n{'=' * 74}")
    if not signals:
        print("  (신규 신호 없음)")
    for i, s in enumerate(signals[:top], 1):
        tag = "🆕" if s["is_new"] else "📈"
        met = []
        if s.get("likes") is not None:
            met.append(f"♥{s['likes']}")
        if s.get("views"):
            met.append(f"▶{s['views']:,}")
        if s.get("delta"):
            met.append(f"+{s['delta']}")
        if s.get("cross"):
            met.append(f"교차{s['cross']}채널")
        if s.get("evergreen"):
            met.append("🕰에버그린")
        print(f"{i:2}. [{s['score']:>5.1f}] {tag} "
              f"{s['channel'][:14]:15} {' '.join(met)}")
        print(f"    {s['caption'][:88]}")
        if s["url"]:
            print(f"    {s['url']}")

    print(f"\n{'-' * 74}\n🆕 신규 게시  📈 좋아요 급상승  교차N채널 = 여러 채널이 같은 소재")
    print("※ 이미지 확보 가능성은 기사 URL이 정해지는 L3 단계에서 판정 (image-rules.md)")
    if failures:
        print(f"\n⚠️  수집 실패 {len(failures)}건 — {', '.join(failures)}")


def check_repeated_failures(con, now):
    """2일 연속 실패한 채널을 찾아낸다. 조용한 실패가 가장 위험하다."""
    since = (datetime.fromisoformat(now) - timedelta(days=3)).isoformat()
    rows = con.execute(
        "SELECT channel, COUNT(*) FROM scan_log "
        "WHERE ok=0 AND seen_at > ? GROUP BY channel HAVING COUNT(*) >= 2",
        (since,)).fetchall()
    return [r[0] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="재수집 없이 리포트만")
    ap.add_argument("--no-youtube", action="store_true")
    args = ap.parse_args()

    con = db_connect()
    now = datetime.now(KST).isoformat(timespec="seconds")
    today = datetime.now(KST).strftime("%Y-%m-%d")
    snap_path = OUT_DIR / f"{today}.json"

    snapshot, failures = [], []

    if args.report and snap_path.exists():
        raw = json.loads(snap_path.read_text(encoding="utf-8"))
        snapshot = [(x["platform"], x["channel"], x["items"]) for x in raw["channels"]]
        failures = raw.get("failures", [])
    else:
        s = new_session()

        for name, _tier in IG_CHANNELS:
            try:
                items, followers = fetch_instagram(s, name)
                snapshot.append(("instagram", name, items))
                record(con, now, "instagram", name, items)
                con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                            (now, "instagram", name, 1, f"{len(items)}건/{followers}팔로워"))
                print(f"  ✅ ig/{name} — {len(items)}건")
            except Exception as e:
                failures.append(f"ig/{name}")
                con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                            (now, "instagram", name, 0, str(e)[:90]))
                print(f"  ❌ ig/{name} — {e}")
            time.sleep(3)

        for name in THREADS_CHANNELS:
            try:
                items = fetch_threads(s, name)
                snapshot.append(("threads", name, items))
                record(con, now, "threads", name, items)
                con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                            (now, "threads", name, 1, f"{len(items)}건"))
                print(f"  ✅ th/{name} — {len(items)}건")
            except Exception as e:
                failures.append(f"th/{name}")
                con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                            (now, "threads", name, 0, str(e)[:90]))
                print(f"  ❌ th/{name} — {e}")
            time.sleep(3)

        if not args.no_youtube:
            for q in YOUTUBE_QUERIES:
                try:
                    items = fetch_youtube(q)
                    snapshot.append(("youtube", f"yt:{q}", items))
                    record(con, now, "youtube", f"yt:{q}", items)
                    con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                                (now, "youtube", f"yt:{q}", 1, f"{len(items)}건"))
                    print(f"  ✅ yt/{q} — {len(items)}건")
                except Exception as e:
                    failures.append(f"yt/{q}")
                    con.execute("INSERT INTO scan_log VALUES (?,?,?,?,?)",
                                (now, "youtube", f"yt:{q}", 0, str(e)[:90]))
                    print(f"  ❌ yt/{q} — {e}")
        con.commit()

    signals = analyse(con, now, snapshot)

    # 전체 스냅샷 — 원자료 포함, 용량이 커서 gitignore 대상 (로컬 분석용)
    snap_path.write_text(json.dumps({
        "scanned_at": now,
        "channels": [{"platform": p, "channel": c, "items": i} for p, c, i in snapshot],
        "failures": failures,
        "signals": signals[:30],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 슬림본 — 이것만 커밋한다.
    # 스케줄 태스크는 클라우드에서 레포를 클론해 돌기 때문에, 커밋되지 않으면
    # 프라이머리 발행 경로가 시그널을 아예 못 봐서 L1 가점이 무용지물이 된다.
    latest = ROOT / "output" / "signals_latest.json"
    latest.write_text(json.dumps({
        "scanned_at": now,
        "failures": failures,
        "signals": [{k: v for k, v in s.items()
                     if k in ("channel", "caption", "url", "score", "topic",
                              "evergreen", "is_new", "likes", "views", "cross")}
                    for s in signals[:20]],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(signals, failures)

    dead = check_repeated_failures(con, now)
    if dead:
        print(f"\n🚨 2일 연속 수집 실패: {', '.join(dead)}")
        print("   → 채널 핸들 변경/차단 여부 확인 필요 (L1이 조용히 죽는 중)")

    print(f"\n💾 {snap_path}")
    con.close()


if __name__ == "__main__":
    main()
