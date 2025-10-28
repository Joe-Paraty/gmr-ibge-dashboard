# ====================================================
# 1. 📚 Importação de bibliotecas
# ====================================================
import os
import io
import glob
import zipfile
import requests
import gdown
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ====================================================
# 2. 🧭 Parâmetros globais
# ====================================================
MAX_SETORES = 5200  # limite máximo de setores

# ====================================================
# 3. 📁 Caminhos (links Google Drive)
# ====================================================
# IDs dos arquivos no Google Drive
DRIVE_SHP_ID = "1NlFEltDlaYxovkorCosZL3bYkryFfFzx"  # ZIP com shapefile
DRIVE_XLSX_ID = "1ge7dKvhHRYxXWENAwnUAsWGzDdcOATvu"  # XLSX com dados e dicionário

# ====================================================
# 4. 🧠 Cache da leitura dos dados
# ====================================================
@st.cache_data
def load_data():
    # -------- 📥 1. Download do SHAPE (ZIP) --------
    shp_url = f"https://drive.google.com/uc?id={DRIVE_SHP_ID}"
    shp_output = "MG_setores_CD2022.zip"
    gdown.download(shp_url, shp_output, quiet=True)

    shp_name_inside_zip = "MG_setores_CD2022.shp"
    gdf = gpd.read_file(f"zip://{shp_output}!{shp_name_inside_zip}")
    gdf["CD_SETOR"] = gdf["CD_SETOR"].astype(str)

    # -------- 📥 2. Download do XLSX --------
    xlsx_url = f"https://drive.google.com/uc?export=download&id={DRIVE_XLSX_ID}"
    r = requests.get(xlsx_url)
    r.raise_for_status()

    df_data = pd.read_excel(io.BytesIO(r.content), sheet_name="DataMG")
    df_data["CD_SETOR"] = df_data["CD_SETOR"].astype(str)

    df_dict = pd.read_excel(io.BytesIO(r.content), sheet_name="dictionary")
    df_dict.columns = (
        df_dict.columns
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
    )

    return gdf, df_data, df_dict

# ====================================================
# 5. 📊 Carregar dados
# ====================================================
gdf, df_data, df_dict = load_data()

# ====================================================
# 6. 🔀 Merge preservando shapefile
# ====================================================
gdf_merged = gdf.merge(df_data, on="CD_SETOR", how="left", suffixes=("", "_data"))

# ====================================================
# 7. 🧭 Preparação dos filtros e variáveis
# ====================================================
dict_var = dict(zip(df_dict["descricao"], df_dict["variavel"]))
descricao_list = list(dict_var.keys())

if "NM_RGINT" not in gdf_merged.columns:
    st.error(f"❌ Coluna NM_RGINT não encontrada. Colunas disponíveis: {gdf_merged.columns.tolist()}")
    st.stop()

regioes = sorted(gdf_merged["NM_RGINT"].dropna().unique())

# ====================================================
# 8. 🌐 Interface Streamlit
# ====================================================
st.set_page_config(page_title="GMR IBGE - Dashboard Censitário", layout="wide")
st.title("🧭 Painel IBGE - Setores Censitários de MG")

# Seletor de variável
variavel_desc = st.selectbox("📈 Selecione a variável:", descricao_list)
variavel_cod = dict_var[variavel_desc]
gdf_merged[variavel_cod] = pd.to_numeric(gdf_merged[variavel_cod], errors="coerce").fillna(0)

# Slider para tolerância de simplificação
tolerancia_simplify = st.slider(
    "🎚️ Ajuste a tolerância da simplificação (quanto maior, mais leve o mapa):",
    min_value=0.0001,
    max_value=0.01,
    value=0.001,
    step=0.0001
)

# Região Intermediária
nm_rgint_sel = st.selectbox("📍 Selecione a Região Intermediária:", regioes, index=0)
gdf_rgint = gdf_merged[gdf_merged["NM_RGINT"] == nm_rgint_sel]

# ====================================================
# 9. 🏙️ Filtro de Município com valor agregado
# ====================================================
agg_mun = (
    gdf_rgint.groupby("NM_MUN")[variavel_cod]
    .sum()
    .reset_index()
    .sort_values(variavel_cod, ascending=False)
)
mun_opts = ["Nenhum"] + [f"{row['NM_MUN']} ({int(row[variavel_cod])})" for _, row in agg_mun.iterrows()]
nm_mun_sel_label = st.selectbox("🏙️ Selecione o Município (valor total entre parênteses):", mun_opts)
nm_mun_sel = nm_mun_sel_label.split(" (")[0] if nm_mun_sel_label != "Nenhum" else "Nenhum"
gdf_mun = gdf_rgint[gdf_rgint["NM_MUN"] == nm_mun_sel] if nm_mun_sel != "Nenhum" else None

# ====================================================
# 10. 🧭 Filtros hierárquicos subsequentes
# ====================================================
dist_opts = sorted(gdf_mun["NM_DIST"].dropna().unique()) if gdf_mun is not None else []
nm_dist_sel = st.selectbox("📍 Selecione o Distrito:", ["Nenhum"] + dist_opts) if gdf_mun is not None else "Nenhum"
gdf_dist = gdf_mun[gdf_mun["NM_DIST"] == nm_dist_sel] if nm_dist_sel != "Nenhum" else None

bairro_opts = sorted(gdf_dist["NM_BAIRRO"].dropna().unique()) if gdf_dist is not None else []
nm_bairro_sel = st.selectbox("🏘️ Selecione o Bairro:", ["Nenhum"] + bairro_opts) if gdf_dist is not None else "Nenhum"
gdf_bairro = gdf_dist[gdf_dist["NM_BAIRRO"] == nm_bairro_sel] if nm_bairro_sel != "Nenhum" else None

# ====================================================
# 11. 🧮 Determinar nível de visualização
# ====================================================
if nm_mun_sel == "Nenhum":
    st.info("Selecione um município para carregar o mapa.")
    st.stop()

if gdf_bairro is not None:
    gdf_filtro = gdf_bairro
elif gdf_dist is not None:
    gdf_filtro = gdf_dist
else:
    gdf_filtro = gdf_mun

# ====================================================
# 12. ⛔ Limite de setores
# ====================================================
if len(gdf_filtro) > MAX_SETORES:
    st.warning(f"⚠️ Área selecionada contém {len(gdf_filtro)} setores — limite máximo é {MAX_SETORES}.")
    st.stop()

# ====================================================
# 13. 🧭 Simplificação das geometrias
# ====================================================
gdf_filtro = gdf_filtro.copy()
gdf_filtro["geometry"] = gdf_filtro["geometry"].simplify(
    tolerance=tolerancia_simplify,
    preserve_topology=True
)

# ====================================================
# 14. 🗺️ Construção do mapa
# ====================================================
bounds = gdf_filtro.total_bounds
center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2

m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="cartodbpositron")

# Choropleth
folium.Choropleth(
    geo_data=gdf_filtro,
    data=gdf_filtro,
    columns=["CD_SETOR", variavel_cod],
    key_on="feature.properties.CD_SETOR",
    fill_color="YlOrRd",
    fill_opacity=0.8,
    line_opacity=0.5,
    legend_name=f"{variavel_desc}"
).add_to(m)

# Tooltip com NM_BAIRRO
folium.GeoJson(
    gdf_filtro,
    name="Setores",
    tooltip=folium.GeoJsonTooltip(
        fields=["CD_SETOR", "NM_BAIRRO", variavel_cod],
        aliases=["Setor:", "Bairro:", f"{variavel_desc}:"],
        localize=True,
        sticky=True,
        labels=True,
        style=(
            "background-color: white; color: black; font-weight: bold; "
            "padding: 5px; border-radius: 5px;"
        )
    )
).add_to(m)

# ====================================================
# 15. 🧮 Agregações condicionais
# ====================================================
st.subheader(f"🗺️ Mapa - {nm_rgint_sel}")
st_folium(m, width=1100, height=600)

# Agregação por distrito (quando município selecionado)
if nm_mun_sel != "Nenhum":
    agg_dist = (
        gdf_mun.groupby("NM_DIST")[variavel_cod]
        .sum()
        .reset_index()
        .sort_values(variavel_cod, ascending=False)
    )
    st.subheader(f"📍 Agregação - Distritos de {nm_mun_sel}")
    st.dataframe(agg_dist)

# Agregação por bairro (quando distrito selecionado)
if nm_dist_sel != "Nenhum":
    agg_bairro = (
        gdf_dist.groupby("NM_BAIRRO")[variavel_cod]
        .sum()
        .reset_index()
        .sort_values(variavel_cod, ascending=False)
    )
    st.subheader(f"🏘️ Agregação - Bairros de {nm_dist_sel}")
    st.dataframe(agg_bairro)

st.caption(
    f"💡 Tolerância de simplificação: {tolerancia_simplify}. "
    f"Limite de {MAX_SETORES} setores. Tooltip mostra NM_BAIRRO."
)
