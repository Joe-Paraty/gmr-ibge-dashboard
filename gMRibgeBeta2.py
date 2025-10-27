# ====================================================
# 1. 📚 Importação de bibliotecas
# ====================================================
import os
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from streamlit_folium import st_folium

# ====================================================
# 2. 🧭 Parâmetros globais
# ====================================================
MAX_SETORES = 5200  # limite máximo de setores
TOLERANCIA_SIMPLIFY = 0.001  # tolerância alta, sem perder qualidade visual

# ====================================================
# 3. 📁 Caminhos
# ====================================================
base_path = r"D:\GMR\2025\CENSO 2022\CODE PYTHON"
shapefile_path = os.path.join(base_path, "MG_setores_CD2022.shp")
data_xlsx_path = os.path.join(base_path, "DataMG.xlsx")

# ====================================================
# 4. 🧠 Cache da leitura dos dados
# ====================================================
@st.cache_data
def load_data():
    gdf = gpd.read_file(shapefile_path)
    gdf["CD_SETOR"] = gdf["CD_SETOR"].astype(str)
    df_data = pd.read_excel(data_xlsx_path, sheet_name="DataMG")
    df_data["CD_SETOR"] = df_data["CD_SETOR"].astype(str)
    df_dict = pd.read_excel(data_xlsx_path, sheet_name="dictionary")
    df_dict.columns = (
        df_dict.columns
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
    )
    return gdf, df_data, df_dict

gdf, df_data, df_dict = load_data()

# ====================================================
# 5. 🔀 Merge preservando shapefile
# ====================================================
gdf_merged = gdf.merge(df_data, on="CD_SETOR", how="left", suffixes=("", "_data"))

# ====================================================
# 6. 🧭 Preparação dos filtros e variáveis
# ====================================================
dict_var = dict(zip(df_dict["descricao"], df_dict["variavel"]))
descricao_list = list(dict_var.keys())

if "NM_RGINT" not in gdf_merged.columns:
    st.error(f"❌ Coluna NM_RGINT não encontrada. Colunas disponíveis: {gdf_merged.columns.tolist()}")
    st.stop()

regioes = sorted(gdf_merged["NM_RGINT"].dropna().unique())

# ====================================================
# 7. 🌐 Interface Streamlit
# ====================================================
st.set_page_config(page_title="GMR IBGE - Dashboard Censitário", layout="wide")
st.title("🧭 Painel IBGE - Setores Censitários de MG")

# Seletor de variável
variavel_desc = st.selectbox("📈 Selecione a variável:", descricao_list)
variavel_cod = dict_var[variavel_desc]
gdf_merged[variavel_cod] = pd.to_numeric(gdf_merged[variavel_cod], errors="coerce").fillna(0)

# Região Intermediária
nm_rgint_sel = st.selectbox("📍 Selecione a Região Intermediária:", regioes, index=0)
gdf_rgint = gdf_merged[gdf_merged["NM_RGINT"] == nm_rgint_sel]

# ====================================================
# 8. 🏙️ Filtro de Município com valor agregado
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
# 9. 🧭 Filtros hierárquicos subsequentes
# ====================================================
dist_opts = sorted(gdf_mun["NM_DIST"].dropna().unique()) if gdf_mun is not None else []
nm_dist_sel = st.selectbox("📍 Selecione o Distrito:", ["Nenhum"] + dist_opts) if gdf_mun is not None else "Nenhum"
gdf_dist = gdf_mun[gdf_mun["NM_DIST"] == nm_dist_sel] if nm_dist_sel != "Nenhum" else None

bairro_opts = sorted(gdf_dist["NM_BAIRRO"].dropna().unique()) if gdf_dist is not None else []
nm_bairro_sel = st.selectbox("🏘️ Selecione o Bairro:", ["Nenhum"] + bairro_opts) if gdf_dist is not None else "Nenhum"
gdf_bairro = gdf_dist[gdf_dist["NM_BAIRRO"] == nm_bairro_sel] if nm_bairro_sel != "Nenhum" else None

# ====================================================
# 10. 🧮 Determinar nível de visualização
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
# 11. ⛔ Limite de setores
# ====================================================
if len(gdf_filtro) > MAX_SETORES:
    st.warning(f"⚠️ Área selecionada contém {len(gdf_filtro)} setores — limite máximo é {MAX_SETORES}.")
    st.stop()

# ====================================================
# 12. 🧭 Simplificação das geometrias
# ====================================================
gdf_filtro = gdf_filtro.copy()
gdf_filtro["geometry"] = gdf_filtro["geometry"].simplify(
    tolerance=TOLERANCIA_SIMPLIFY,
    preserve_topology=True
)

# ====================================================
# 13. 🗺️ Construção do mapa
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

# Tooltip com texto escuro
folium.GeoJson(
    gdf_filtro,
    name="Setores",
    tooltip=folium.GeoJsonTooltip(
        fields=["CD_SETOR", "NM_MUN", variavel_cod],
        aliases=["Setor:", "Município:", f"{variavel_desc}:"],
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
# 14. 🧮 Agregações condicionais
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
    f"💡 Tolerância de simplificação: {TOLERANCIA_SIMPLIFY}. "
    f"Limite de {MAX_SETORES} setores. Tooltip otimizado com texto escuro."
)
