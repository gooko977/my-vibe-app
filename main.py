"""
전국 고령화 지도 - Streamlit 앱
--------------------------------
시군구별 65세 이상 인구 비율(고령화율)을 5단계 색으로 나눠 지도에 표시합니다.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests

# ---------------------------------------------------------
# 1. 화면 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="전국 고령화 지도", layout="wide")
st.title("🇰🇷 전국 시군구별 고령화 지도")
st.caption("시군구별 65세 이상 인구 비율(고령화율)을 색으로 나타낸 지도입니다.")

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


# ---------------------------------------------------------
# 3. 시군구 코드 만들기 & 가장 최신 연도만 사용하기
# ---------------------------------------------------------
# '코드'(행정동 코드)의 앞 5자리가 시군구를 나타냅니다.
df["시군구코드"] = df["코드"].str[:5]

# 가장 최신 연도를 자동으로 찾습니다.
latest_year = df["연도"].max()
df_latest = df[df["연도"] == latest_year].copy()

st.write(f"### {latest_year}년 기준 고령화 지도")


# ---------------------------------------------------------
# 4. 나이별 인구 열 중에서 '계_' (남녀 합계)로 시작하는 열만 골라내기
# ---------------------------------------------------------
age_cols = [c for c in df.columns if c.startswith("계_")]


def get_age_number(col_name: str) -> int:
    """'계_0세' -> 0, '계_100세 이상' -> 100 처럼 나이 숫자만 뽑아내는 함수"""
    text = col_name.replace("계_", "").replace("세 이상", "").replace("세", "")
    return int(text)


# 65세 이상에 해당하는 열만 따로 모읍니다.
age65_cols = [c for c in age_cols if get_age_number(c) >= 65]

# 시군구코드 + 읍면동 단위로 총인구, 65세 이상 인구를 계산합니다.
df_latest["총인구"] = df_latest[age_cols].sum(axis=1)
df_latest["고령인구"] = df_latest[age65_cols].sum(axis=1)


# ---------------------------------------------------------
# 5. 읍면동 단위 데이터를 시군구 단위로 합치기
# ---------------------------------------------------------
grouped = (
    df_latest.groupby("시군구코드")
    .agg(
        시도=("시도", "first"),
        시군구=("시군구", "first"),
        총인구=("총인구", "sum"),
        고령인구=("고령인구", "sum"),
    )
    .reset_index()
)

# 고령화율(%) 계산
grouped["고령화율"] = (grouped["고령인구"] / grouped["총인구"] * 100).round(2)
# 지도에 마우스를 올렸을 때 보여줄 글자(%) 만들기
grouped["고령화율_표시"] = grouped["고령화율"].astype(str) + "%"


# ---------------------------------------------------------
# 6. 고령화율을 5단계 구간으로 나누기
# ---------------------------------------------------------
# 구간 경계값: 19%, 23%, 28%, 38% (전국 시군구를 5등분한 실제 값)
구간_경계값 = [-np.inf, 19, 23, 28, 38, np.inf]
구간_이름 = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]

grouped["구간"] = pd.cut(grouped["고령화율"], bins=구간_경계값, labels=구간_이름)

# 낮은 단계는 옅은 색, 높은 단계는 진한 색
구간_색 = ["#fee8c8", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"]
색_매핑 = dict(zip(구간_이름, 구간_색))


# ---------------------------------------------------------
# 7. 지도 그리기 (배경 타일 없이 경계선만 표시)
# ---------------------------------------------------------
fig = px.choropleth(
    grouped,
    geojson=geojson,
    locations="시군구코드",          # 우리 데이터의 코드 열
    featureidkey="properties.코드",  # geojson 쪽 코드 속성 이름 (이름이 아닌 코드로 매칭!)
    color="구간",
    category_orders={"구간": 구간_이름},
    color_discrete_map=색_매핑,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율_표시": True,
        "시군구코드": False,
        "구간": False,
    },
    labels={"고령화율_표시": "고령화율", "시도": "시도"},
)

# 배경 지도(타일)를 숨기고, 우리 경계선만 화면에 딱 맞게 보여줍니다.
fig.update_geos(visible=False, fitbounds="locations")
fig.update_layout(
    margin=dict(l=0, r=0, t=0, b=0),
    legend_title_text="65세 이상 인구 비율",
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# 8. 고령화율 높은 지역 / 낮은 지역 표 나란히 보여주기
# ---------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔺 고령화율 높은 지역 TOP 10")
    top10 = (
        grouped.sort_values("고령화율", ascending=False)
        .head(10)[["시도", "시군구", "고령화율"]]
        .reset_index(drop=True)
    )
    top10.index = top10.index + 1  # 1등부터 보이도록 번호 조정
    st.table(top10)

with col2:
    st.subheader("🔻 고령화율 낮은 지역 TOP 10")
    bottom10 = (
        grouped.sort_values("고령화율", ascending=True)
        .head(10)[["시도", "시군구", "고령화율"]]
        .reset_index(drop=True)
    )
    bottom10.index = bottom10.index + 1
    st.table(bottom10)
