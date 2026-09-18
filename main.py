"""
전국 인구 지도 - Streamlit 앱
--------------------------------
시군구별 인구 비율(유소년 / 고령)을 색으로 나눠 지도에 표시합니다.
왼쪽 옵션에서 연도 · 인구 종류 · 지역을 바꿔가며 볼 수 있습니다.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests

# ---------------------------------------------------------
# 1. 화면 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="전국 인구 지도", layout="wide")
st.title("🇰🇷 전국 시군구별 인구 지도")
st.caption("연도 · 인구 종류 · 지역을 골라서 시군구별 비율을 지도로 확인해 보세요.")

# 데이터가 있는 주소
POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


# ---------------------------------------------------------
# 2. 데이터 불러오기 (한 번 불러오면 캐시에 저장해서 재사용)
# ---------------------------------------------------------
@st.cache_data
def load_population():
    """인구 데이터(csv.gz)를 불러옵니다."""
    # '코드' 열은 계산용 숫자가 아니라 이름표(문자열)이므로 dtype=str로 지정합니다.
    # 그렇지 않으면 앞자리 0이 사라지는 등 문제가 생깁니다.
    df = pd.read_csv(POP_URL, compression="gzip", dtype={"코드": str})
    return df


@st.cache_data
def load_geojson():
    """시군구 경계선(geojson)을 불러옵니다."""
    response = requests.get(GEO_URL)
    return response.json()


df = load_population()
geojson = load_geojson()

# '코드'(행정동 코드)의 앞 5자리가 시군구를 나타냅니다.
df["시군구코드"] = df["코드"].str[:5]

# 나이별 인구 열 중에서 '계_' (남녀 합계)로 시작하는 열만 골라내기
age_cols = [c for c in df.columns if c.startswith("계_")]


def get_age_number(col_name: str) -> int:
    """'계_0세' -> 0, '계_100세 이상' -> 100 처럼 나이 숫자만 뽑아내는 함수"""
    text = col_name.replace("계_", "").replace("세 이상", "").replace("세", "")
    return int(text)


# ---------------------------------------------------------
# 3. 사이드바 옵션 (연도 / 인구 종류 / 지역)
# ---------------------------------------------------------
st.sidebar.header("⚙️ 옵션")

# ① 연도 선택 (최신 연도가 기본으로 선택되도록 맨 위에 둠)
연도_목록 = sorted(df["연도"].unique(), reverse=True)
선택_연도 = st.sidebar.selectbox("연도 선택", 연도_목록, index=0)

# ② 인구 종류 선택 (유소년 인구 / 고령 인구)
인구종류 = st.sidebar.radio(
    "인구 종류 선택",
    ["고령 인구 비율 (65세 이상)", "유소년 인구 비율 (0~14세)"],
)

# 선택한 인구 종류에 따라 나이 범위를 다르게 지정합니다.
if 인구종류 == "고령 인구 비율 (65세 이상)":
    대상_age_cols = [c for c in age_cols if get_age_number(c) >= 65]
    지표명 = "고령화율"
else:
    대상_age_cols = [c for c in age_cols if get_age_number(c) <= 14]
    지표명 = "유소년 인구 비율"

# ③ 지역(시도) 선택 - '전국'을 고르면 전체 지도를 보여줍니다.
시도_목록 = ["전국"] + sorted(df["시도"].unique())
선택_시도 = st.sidebar.selectbox("지역 선택 (시도)", 시도_목록, index=0)

# ④ 인구를 그래프로도 한눈에 보고 싶을 때 켜는 옵션
그래프_표시 = st.sidebar.checkbox("📊 인구 그래프로 보기", value=True)


st.write(f"### {선택_연도}년 · {지표명} · {선택_시도}")


# ---------------------------------------------------------
# 4. 선택한 연도로 필터링 후 시군구 단위로 합치기
# ---------------------------------------------------------
df_year = df[df["연도"] == 선택_연도].copy()

df_year["총인구"] = df_year[age_cols].sum(axis=1)
df_year["대상인구"] = df_year[대상_age_cols].sum(axis=1)

grouped = (
    df_year.groupby("시군구코드")
    .agg(
        시도=("시도", "first"),
        시군구=("시군구", "first"),
        총인구=("총인구", "sum"),
        대상인구=("대상인구", "sum"),
    )
    .reset_index()
)

# 비율(%) 계산
grouped["비율"] = (grouped["대상인구"] / grouped["총인구"] * 100).round(2)
# 지도에 마우스를 올렸을 때 보여줄 글자(%) 만들기
grouped["비율_표시"] = grouped["비율"].astype(str) + "%"

# 지역(시도) 옵션이 '전국'이 아니면 해당 시도만 남깁니다.
if 선택_시도 != "전국":
    grouped = grouped[grouped["시도"] == 선택_시도].reset_index(drop=True)


# ---------------------------------------------------------
# 5. 비율을 5단계 구간으로 나누기 (지금 화면에 보이는 데이터 기준 5등분)
# ---------------------------------------------------------
# 연도·인구 종류·지역에 따라 값의 범위가 달라지므로,
# 고정된 숫자 대신 지금 데이터를 5등분한 실제 값(분위수)으로 구간을 나눕니다.
분위수 = grouped["비율"].quantile([0, 0.2, 0.4, 0.6, 0.8, 1.0]).values
경계값 = sorted(set(np.round(분위수, 1)))  # 중복된 경계값 제거

# 구간이 5개보다 적게 나오는 경우(값이 거의 같을 때)를 대비한 안전 장치
if len(경계값) < 6:
    최소값, 최대값 = grouped["비율"].min(), grouped["비율"].max()
    경계값 = list(np.linspace(최소값, 최대값, 6))

구간_경계값 = [-np.inf] + list(경계값[1:-1]) + [np.inf]
구간_이름 = [
    f"{경계값[1]}% 미만",
    f"{경계값[1]}% ~ {경계값[2]}%",
    f"{경계값[2]}% ~ {경계값[3]}%",
    f"{경계값[3]}% ~ {경계값[4]}%",
    f"{경계값[4]}% 이상",
]

grouped["구간"] = pd.cut(grouped["비율"], bins=구간_경계값, labels=구간_이름)

# 초록색 계열: 옅은 초록 -> 진한 초록 (심플하고 한눈에 들어오는 단일 색조)
구간_색 = ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]
색_매핑 = dict(zip(구간_이름, 구간_색))


# ---------------------------------------------------------
# 6. 지도에 표시할 시군구 경계선만 골라내기 (지역 선택 시 해당 지역만 남김)
# ---------------------------------------------------------
if 선택_시도 != "전국":
    남길_코드 = set(grouped["시군구코드"])
    geojson_표시용 = {
        "type": "FeatureCollection",
        "features": [
            f for f in geojson["features"] if f["properties"]["코드"] in 남길_코드
        ],
    }
else:
    geojson_표시용 = geojson


# ---------------------------------------------------------
# 7. 지도 그리기 (배경 타일 없이 경계선만, 초록색 5단계)
# ---------------------------------------------------------
fig = px.choropleth(
    grouped,
    geojson=geojson_표시용,
    locations="시군구코드",          # 우리 데이터의 코드 열
    featureidkey="properties.코드",  # geojson 쪽 코드 속성 이름 (이름이 아닌 코드로 매칭!)
    color="구간",
    category_orders={"구간": 구간_이름},
    color_discrete_map=색_매핑,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "비율_표시": True,
        "시군구코드": False,
        "구간": False,
    },
    labels={"비율_표시": 지표명, "시도": "시도"},
)

# 배경 지도(타일)를 숨기고, 경계선만 화면에 딱 맞게 보여줍니다.
fig.update_geos(visible=False, fitbounds="locations")

# 심플한 디자인: 여백을 줄이고, 경계선을 얇고 옅게
fig.update_traces(marker_line_width=0.5, marker_line_color="white", selector=dict(type="choropleth"))

fig.update_layout(
    margin=dict(l=0, r=0, t=0, b=0),
    legend_title_text=지표명,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.15,
        xanchor="center",
        x=0.5,
    ),
    font=dict(size=13),
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# 8. 인구를 그래프로 한눈에 보기 (연도별 추이 + 연령대별 분포)
# ---------------------------------------------------------
if 그래프_표시:
    st.markdown("---")
    st.subheader(f"📊 {선택_시도} 인구 한눈에 보기")

    # 지역(시도) 선택에 맞춰 원본 데이터를 좁혀 둡니다.
    if 선택_시도 != "전국":
        df_지역 = df[df["시도"] == 선택_시도]
    else:
        df_지역 = df

    그래프_col1, 그래프_col2 = st.columns(2)

    # --- ① 연도별 총인구 추이 (선 그래프) ---
    with 그래프_col1:
        st.markdown(f"**연도별 총인구 추이 ({선택_시도})**")
        연도별_총인구 = (
            df_지역.assign(총인구=df_지역[age_cols].sum(axis=1))
            .groupby("연도")["총인구"]
            .sum()
            .reset_index()
        )
        추이_fig = px.line(
            연도별_총인구,
            x="연도",
            y="총인구",
            markers=True,
        )
        # 심플한 초록색 라인으로 통일
        추이_fig.update_traces(line_color="#31a354", marker_color="#006d2c")
        추이_fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="총인구(명)",
            xaxis_title="연도",
        )
        st.plotly_chart(추이_fig, use_container_width=True)

    # --- ② 선택 연도의 연령대별 인구 분포 (막대 그래프, 5세 단위) ---
    with 그래프_col2:
        st.markdown(f"**{선택_연도}년 연령대별 인구 분포 ({선택_시도})**")

        df_지역_연도 = df_지역[df_지역["연도"] == 선택_연도]

        def get_age_bucket(col_name: str) -> str:
            """나이를 5살 단위로 묶어서 '0~4세' 같은 구간 이름을 만드는 함수"""
            나이 = get_age_number(col_name)
            if 나이 >= 100:
                return "100세 이상"
            시작 = (나이 // 5) * 5
            return f"{시작}~{시작+4}세"

        연령대_인구 = {}
        for col in age_cols:
            구간 = get_age_bucket(col)
            연령대_인구[구간] = 연령대_인구.get(구간, 0) + df_지역_연도[col].sum()

        연령대_순서 = sorted(
            연령대_인구.keys(),
            key=lambda x: 999 if x == "100세 이상" else int(x.split("~")[0]),
        )
        연령대_df = pd.DataFrame(
            {"연령대": 연령대_순서, "인구수": [연령대_인구[k] for k in 연령대_순서]}
        )

        분포_fig = px.bar(연령대_df, x="연령대", y="인구수")
        분포_fig.update_traces(marker_color="#31a354")
        분포_fig.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="인구수(명)",
            xaxis_title="연령대",
        )
        st.plotly_chart(분포_fig, use_container_width=True)


# ---------------------------------------------------------
# 9. 비율 높은 지역 / 낮은 지역 표 나란히 보여주기
# ---------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader(f"🔺 {지표명} 높은 지역 TOP 10")
    top10 = (
        grouped.sort_values("비율", ascending=False)
        .head(10)[["시도", "시군구", "비율"]]
        .reset_index(drop=True)
    )
    top10.index = top10.index + 1  # 1등부터 보이도록 번호 조정
    top10 = top10.rename(columns={"비율": 지표명})
    st.table(top10)

with col2:
    st.subheader(f"🔻 {지표명} 낮은 지역 TOP 10")
    bottom10 = (
        grouped.sort_values("비율", ascending=True)
        .head(10)[["시도", "시군구", "비율"]]
        .reset_index(drop=True)
    )
    bottom10.index = bottom10.index + 1
    bottom10 = bottom10.rename(columns={"비율": 지표명})
    st.table(bottom10)
