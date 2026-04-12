"""
뉴스 게시물 생성기 — Streamlit 웹앱
두 가지 모드:
  1. 기사 URL 자동 → URL만 넣으면 제목/이미지/출처 자동 추출
  2. 수동 입력 → 헤드라인 + 이미지 + 출처 직접 입력
"""

import os
import tempfile

import streamlit as st
from PIL import Image
from io import BytesIO
from datetime import date

st.set_page_config(
    page_title="피아트 뉴스 썸네일",
    page_icon="🎨",
    layout="centered",
)

from tools.news_poster import generate_news_poster
from tools.article_parser import parse_article

HEADLINE_MAX = 11  # 공백 포함 권장 최대 글자수


def _char_count_label(text: str, label: str) -> str:
    """글자수 카운터 (11자 초과 시 경고)."""
    n = len(text)
    if n == 0:
        return ""
    if n > HEADLINE_MAX:
        return f"⚠️ {label}: {n}자 (권장 {HEADLINE_MAX}자 이하 — 넘으면 잘릴 수 있음)"
    return f"✅ {label}: {n}자"


def _generate_and_show(h1, h2, source, image_url, uploaded_file, badge, scale, logo_color="auto"):
    """이미지 생성 → 미리보기 → 다운로드 버튼."""
    tmp_image_path = None
    if uploaded_file:
        suffix = os.path.splitext(uploaded_file.name)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uploaded_file.read())
        tmp.close()
        tmp_image_path = tmp.name

    with st.spinner("이미지 생성 중..."):
        try:
            out_path = tempfile.mktemp(suffix=".png")
            generate_news_poster(
                headline1=h1,
                headline2=h2,
                source=source if source else "",
                image_url=image_url,
                image_path=tmp_image_path,
                badge_text=badge if badge else None,
                output_path=out_path,
                scale=scale,
                logo_color=logo_color,
            )
            result_img = Image.open(out_path)
        except Exception as e:
            st.error(f"생성 실패: {e}")
            st.stop()

    st.success("생성 완료!")
    st.image(result_img, use_container_width=True)

    buf = BytesIO()
    result_img.save(buf, format="PNG")
    slug = h1.replace(" ", "_")[:10]
    filename = f"{date.today().isoformat()}_{slug}.png"

    st.download_button(
        label="PNG 다운로드",
        data=buf.getvalue(),
        file_name=filename,
        mime="image/png",
        use_container_width=True,
    )

    if tmp_image_path and os.path.exists(tmp_image_path):
        os.unlink(tmp_image_path)
    if os.path.exists(out_path):
        os.unlink(out_path)


# ── 페이지 레이아웃 ──
st.markdown(
    "<style>.stApp { max-width: 720px; margin: 0 auto; }</style>",
    unsafe_allow_html=True,
)

st.title("피아트 뉴스 썸네일 생성기")
st.caption("인스타그램용 뉴스 썸네일(1080×1350)을 만들어줍니다.")

tab_auto, tab_manual = st.tabs(["📰 기사 URL로 자동 생성", "✏️ 수동 입력"])

# ══════════════════════════════════════════════
# 탭 1: 기사 URL 자동
# ══════════════════════════════════════════════
with tab_auto:
    article_url = st.text_input(
        "기사 URL",
        placeholder="https://www.yna.co.kr/view/AKR...",
        key="article_url",
    )

    if st.button("기사 분석", key="parse_btn", use_container_width=True):
        if not article_url:
            st.error("기사 URL을 입력해주세요.")
        else:
            with st.spinner("기사 분석 중..."):
                try:
                    meta = parse_article(article_url)
                    st.session_state["parsed"] = meta
                except Exception as e:
                    st.error(f"기사 파싱 실패: {e}")

    if "parsed" in st.session_state:
        meta = st.session_state["parsed"]

        st.success(f"기사 분석 완료: {meta.get('site_name', '')}")

        with st.form("auto_form"):
            st.markdown("**자동 추출 결과** (수정 가능)")
            st.caption(f"원제: {meta.get('title', '')[:80]}")

            auto_h1 = st.text_input(
                f"헤드라인 1줄 (권장 {HEADLINE_MAX}자 이내)",
                value="", placeholder="6~9자 직접 작성",
                key="auto_h1",
            )
            auto_h2 = st.text_input(
                f"헤드라인 2줄 (권장 {HEADLINE_MAX}자 이내)",
                value="", placeholder="6~9자 직접 작성",
                key="auto_h2",
            )
            # 글자수 카운터
            c1 = _char_count_label(auto_h1, "1줄")
            c2 = _char_count_label(auto_h2, "2줄")
            if c1 or c2:
                st.caption(f"{c1}{'  |  ' if c1 and c2 else ''}{c2}")

            auto_source = st.text_input(
                "출처 (비우면 자동 적용)",
                value=f"© {meta.get('source', '')}",
                key="auto_source",
            )

            if meta.get("image_url"):
                st.image(meta["image_url"], caption="추출된 이미지", use_container_width=True)
            auto_image_url = st.text_input(
                "이미지 URL (수정 가능)",
                value=meta.get("image_url", ""),
                key="auto_img",
            )

            auto_uploaded = st.file_uploader(
                "또는 이미지 직접 업로드",
                type=["jpg", "jpeg", "png", "webp"],
                key="auto_upload",
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                auto_badge = st.text_input("뱃지 (선택)", key="auto_badge")
            with col2:
                auto_logo_color = st.selectbox(
                    "로고 색상", ["자동", "흰색", "검정"],
                    index=0, key="auto_logo",
                )
            with col3:
                auto_scale = st.selectbox(
                    "배율", [1, 2], index=0,
                    format_func=lambda x: f"{x}x ({1080*x}×{1350*x})",
                    key="auto_scale",
                )

            auto_submit = st.form_submit_button("썸네일 생성", use_container_width=True, type="primary")

        if auto_submit:
            if not auto_h1 or not auto_h2:
                st.error("헤드라인 1줄, 2줄을 입력해주세요.")
            elif not auto_image_url and not auto_uploaded:
                st.error("이미지 URL 또는 파일이 필요합니다.")
            else:
                final_source = auto_source if auto_source else f"© {meta.get('source', meta.get('site_name', ''))}"
                logo_map = {"자동": "auto", "흰색": "white", "검정": "black"}
                _generate_and_show(
                    auto_h1, auto_h2, final_source,
                    auto_image_url if not auto_uploaded else None,
                    auto_uploaded,
                    auto_badge, auto_scale,
                    logo_color=logo_map[auto_logo_color],
                )

# ══════════════════════════════════════════════
# 탭 2: 수동 입력
# ══════════════════════════════════════════════
with tab_manual:
    with st.form("manual_form"):
        headline1 = st.text_input(
            f"헤드라인 1줄 (권장 {HEADLINE_MAX}자 이내)",
            placeholder="국립현대미술관",
            key="m_h1",
        )
        headline2 = st.text_input(
            f"헤드라인 2줄 (권장 {HEADLINE_MAX}자 이내)",
            placeholder="전시 관람료 인상",
            key="m_h2",
        )
        c1 = _char_count_label(headline1, "1줄")
        c2 = _char_count_label(headline2, "2줄")
        if c1 or c2:
            st.caption(f"{c1}{'  |  ' if c1 and c2 else ''}{c2}")

        source = st.text_input("출처 (선택)", placeholder="© 국립현대미술관", key="m_src")

        st.divider()
        st.markdown("**배경 이미지** (둘 중 하나)")
        image_url = st.text_input("이미지 URL", placeholder="https://example.com/photo.jpg", key="m_url")
        uploaded_file = st.file_uploader("또는 파일 업로드", type=["jpg", "jpeg", "png", "webp"], key="m_upload")

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            badge_text = st.text_input("뱃지 (선택)", key="m_badge")
        with col2:
            m_logo_color = st.selectbox(
                "로고 색상", ["자동", "흰색", "검정"],
                index=0, key="m_logo",
            )
        with col3:
            scale = st.selectbox(
                "배율", [1, 2], index=0,
                format_func=lambda x: f"{x}x ({1080*x}×{1350*x})",
                key="m_scale",
            )

        submitted = st.form_submit_button("썸네일 생성", use_container_width=True, type="primary")

    if submitted:
        if not headline1 or not headline2:
            st.error("헤드라인 1줄, 2줄을 모두 입력해주세요.")
        elif not image_url and not uploaded_file:
            st.error("배경 이미지 URL 또는 파일을 넣어주세요.")
        else:
            logo_map = {"자동": "auto", "흰색": "white", "검정": "black"}
            _generate_and_show(
                headline1, headline2, source if source else "",
                image_url if not uploaded_file else None,
                uploaded_file,
                badge_text, scale,
                logo_color=logo_map[m_logo_color],
            )
