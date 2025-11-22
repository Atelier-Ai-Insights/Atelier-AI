import streamlit as st
import pandas as pd
# Importación consolidada incluyendo clean_gemini_json
from utils import get_relevant_info, get_stopwords, clean_gemini_json
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase
from prompts import (
    get_survey_articulation_prompt, get_excel_autocode_prompt,
    get_data_summary_prompt, get_correlation_prompt, get_stat_test_prompt 
)
import constants as c
import io 
import os 
import uuid 
from datetime import datetime
import re 
import json 
import traceback 
import seaborn as sns
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
import scipy.stats as stats
import numpy as np

# =====================================================
# MODO: ANÁLISIS NUMÉRICO (EXCEL) - VERSIÓN PROYECTOS
# =====================================================

PROJECT_BUCKET = "project_files"

# --- Funciones Helper ---

# NOTA: Se eliminó la función local clean_gemini_json porque ya se importa desde utils.py

@st.cache_data
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Pivot', index=True)
    return output.getvalue()

def style_residuals(val):
    if val > 1.96:
        return 'background-color: #d4edda; color: #155724' 
    elif val < -1.96:
        return 'background-color: #f8d7da; color: #721c24' 
    else:
        return 'color: #333'

def add_title_slide(prs, title_text):
    try:
        slide_layout = prs.slide_layouts[0] 
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        title.text = title_text
    except Exception as e:
        print(f"Error al añadir slide de título: {e}")

def add_image_slide(prs, title_text, image_stream):
    try:
        slide_layout = prs.slide_layouts[5] 
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        title.text = title_text
        image_stream.seek(0)
        slide.shapes.add_picture(image_stream, Inches(0.5), Inches(1.5), width=Inches(9))
    except Exception as e:
        print(f"Error al añadir slide de imagen: {e}")

def add_table_slide(prs, title_text, df):
    try:
        slide_layout = prs.slide_layouts[5] 
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        title.text = title_text

        if df.index.name or isinstance(df.index, pd.MultiIndex):
            df_to_add = df.reset_index()
        else:
            df_to_add = df
            
        rows, cols = df_to_add.shape
        left = Inches(0.5); top = Inches(1.5); width = Inches(9.0); height = Inches(5.5)
        graphic_frame = slide.shapes.add_table(rows + 1, cols, left, top, width, height)
        table = graphic_frame.table

        for c in range(cols):
            table.cell(0, c).text = str(df_to_add.columns[c])
            table.cell(0, c).text_frame.paragraphs[0].font.bold = True

        for r in range(rows):
            for c in range(cols):
                table.cell(r + 1, c).text = str(df_to_add.iloc[r, c])
                
    except Exception as e:
        print(f"Error al añadir slide de tabla: {e}")

# --- Funciones de Gestión de Proyectos ---

@st.cache_data(ttl=600, show_spinner=False)
def load_project_data(storage_path):
    try:
        response = supabase.storage.from_(PROJECT_BUCKET).create_signed_url(storage_path, 60)
        signed_url = response['signedURL']
        df = pd.read_excel(signed_url)
        return df
    except Exception as e:
        st.error(f"Error al cargar el proyecto: {e}")
        return None

def show_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto")
    
    try:
        response = supabase.table("projects").select("id", count='exact').eq("user_id", user_id).execute()
        project_count = response.count
    except Exception as e:
        st.error(f"Error al verificar el conteo de proyectos: {e}")
        return

    if project_count >= plan_limit and plan_limit != float('inf'):
        st.warning(f"Has alcanzado el límite de {int(plan_limit)} proyectos para tu plan actual.")
        return

    with st.form("new_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Tracking de Ventas Q1 2024")
        project_brand = st.text_input("Marca*", placeholder="Ej: Marca X")
        project_year = st.number_input("Año*", min_value=2020, max_value=2030, value=datetime.now().year)
        uploaded_file = st.file_uploader("Archivo Excel (.xlsx)*", type=["xlsx"])
        
        submitted = st.form_submit_button("Crear Proyecto")

    if submitted:
        if not all([project_name, project_brand, project_year, uploaded_file]):
            st.warning("Por favor, completa todos los campos.")
            return

        with st.spinner("Creando proyecto y subiendo archivo..."):
            try:
                file_bytes = uploaded_file.getvalue()
                file_ext = os.path.splitext(uploaded_file.name)[1]
                storage_path = f"{user_id}/{uuid.uuid4()}{file_ext}" 
                
                supabase.storage.from_(PROJECT_BUCKET).upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
                )
                
                project_data = {
                    "project_name": project_name,
                    "project_brand": project_brand,
                    "project_year": int(project_year),
                    "storage_path": storage_path,
                    "user_id": user_id
                }
                
                supabase.table("projects").insert(project_data).execute()
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")

def show_project_list(user_id):
    st.subheader("Mis Proyectos")
    try:
        response = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e: st.error(f"Error al cargar lista: {e}"); return

    if not projects: st.info("Aún no has creado ningún proyecto."); return

    for proj in projects:
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{proj['project_name']}**")
                st.caption(f"Marca: {proj.get('project_brand')} | Año: {proj.get('project_year')}")
            with col2:
                if st.button("Analizar", key=f"analizar_{proj['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state["da_selected_project_id"] = proj['id']
                    st.session_state.mode_state["da_selected_project_name"] = proj['project_name']
                    st.session_state.mode_state["da_storage_path"] = proj['storage_path']
                    st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
                    st.rerun()
            with col3:
                if st.button("Eliminar", key=f"eliminar_{proj['id']}", width='stretch'):
                    try:
                        supabase.storage.from_(PROJECT_BUCKET).remove([proj['storage_path']])
                        supabase.table("projects").delete().eq("id", proj['id']).execute()
                        st.success("Proyecto eliminado."); st.rerun()
                    except Exception as e: st.error(f"Error al eliminar: {e}")

# --- FUNCIÓN show_project_analyzer (OPTIMIZADA) ---
def show_project_analyzer(df, db_filtered, selected_files):
    
    plan_features = st.session_state.plan_features
    
    def set_da_sub_mode(new_mode):
        st.session_state.mode_state["da_current_sub_mode"] = new_mode

    if "da_current_sub_mode" not in st.session_state.mode_state:
        st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
    
    # Lógica de permisos de plan (simplificada para legibilidad)
    current_default = st.session_state.mode_state["da_current_sub_mode"]
    feature_map = {
        "Resumen Ejecutivo IA": "da_has_summary", "Auto-Codificación": "da_has_autocode",
        "Nube de Palabras": "da_has_wordcloud", "Exportar a PPT": "da_has_ppt_export",
        "Análisis Rápido": "da_has_quick_analysis", "Tabla Dinámica": "da_has_pivot_table",
        "Análisis de Correlación": "da_has_correlation", "Comparación de Grupos": "da_has_group_comparison"
    }
    
    if not plan_features.get(feature_map.get(current_default, ""), False):
        # Fallback si no tiene permiso
        if plan_features.get("da_has_summary"): st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
        elif plan_features.get("da_has_quick_analysis"): st.session_state.mode_state["da_current_sub_mode"] = "Análisis Rápido"

    sub_modo = st.session_state.mode_state["da_current_sub_mode"]
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}; st.rerun()
        
    st.markdown("##### Selecciona una función de análisis:")
    col_ia, col_stats = st.columns(2)

    with col_ia:
        with st.expander("📊 Funciones de IA Generativa", expanded=True):
            if plan_features.get("da_has_summary"):
                st.button("Resumen Ejecutivo", on_click=set_da_sub_mode, args=("Resumen Ejecutivo IA",), width='stretch', type="primary" if sub_modo == "Resumen Ejecutivo IA" else "secondary")
            if plan_features.get("da_has_autocode"):
                st.button("Auto-Codificación", on_click=set_da_sub_mode, args=("Auto-Codificación",), width='stretch', type="primary" if sub_modo == "Auto-Codificación" else "secondary")
            if plan_features.get("da_has_wordcloud"):
                st.button("Nube de Palabras", on_click=set_da_sub_mode, args=("Nube de Palabras",), width='stretch', type="primary" if sub_modo == "Nube de Palabras" else "secondary")
            if plan_features.get("da_has_ppt_export"):
                st.button("Exportar a PPT", on_click=set_da_sub_mode, args=("Exportar a PPT",), width='stretch', type="primary" if sub_modo == "Exportar a PPT" else "secondary")

    with col_stats:
        with st.expander("📈 Análisis Estadístico y Cruces", expanded=True):
            if plan_features.get("da_has_quick_analysis"):
                st.button("Análisis Rápido", on_click=set_da_sub_mode, args=("Análisis Rápido",), width='stretch', type="primary" if sub_modo == "Análisis Rápido" else "secondary")
            if plan_features.get("da_has_pivot_table"):
                st.button("Tabla Dinámica", on_click=set_da_sub_mode, args=("Tabla Dinámica",), width='stretch', type="primary" if sub_modo == "Tabla Dinámica" else "secondary")
            if plan_features.get("da_has_correlation"):
                st.button("Análisis de Correlación", on_click=set_da_sub_mode, args=("Análisis de Correlación",), width='stretch', type="primary" if sub_modo == "Análisis de Correlación" else "secondary")
            if plan_features.get("da_has_group_comparison"):
                st.button("Comparación de Grupos", on_click=set_da_sub_mode, args=("Comparación de Grupos",), width='stretch', type="primary" if sub_modo == "Comparación de Grupos" else "secondary")

    st.divider()
    
    if "data_analysis_stats_context" not in st.session_state.mode_state:
        st.session_state.mode_state["data_analysis_stats_context"] = ""
    
    # --- SUB-MODO: RESUMEN EJECUTIVO ---
    if sub_modo == "Resumen Ejecutivo IA":
        st.header("Resumen Ejecutivo")
        if "da_summary_result" in st.session_state.mode_state:
            st.markdown(st.session_state.mode_state["da_summary_result"])
            if st.button("Generar nuevo resumen", width='stretch', type="secondary"):
                st.session_state.mode_state.pop("da_summary_result"); st.rerun()
        else:
            if st.button("Generar Resumen Ejecutivo", width='stretch', type="primary"):
                with st.spinner("Analizando la estructura de los datos..."):
                    try:
                        snapshot_buffer = io.StringIO()
                        snapshot_buffer.write(f"Total Filas: {len(df)}\n\n")
                        df.info(buf=snapshot_buffer, verbose=False)
                        numeric_cols = df.select_dtypes(include=['number']).columns
                        if not numeric_cols.empty:
                            snapshot_buffer.write("\nMétricas Numéricas:\n")
                            snapshot_buffer.write(df[numeric_cols].describe().to_string(float_format="%.2f"))
                        cat_cols = df.select_dtypes(include=['object', 'category']).columns
                        if not cat_cols.empty:
                            snapshot_buffer.write("\nDistribución Categórica (Top 5):\n")
                            for col in cat_cols:
                                if df[col].nunique() < 50: 
                                    snapshot_buffer.write(f"\n{col}:\n")
                                    snapshot_buffer.write(df[col].value_counts(normalize=True).head(5).to_string(float_format="%.1f%%"))
                        
                        prompt = get_data_summary_prompt(snapshot_buffer.getvalue())
                        response = call_gemini_api(prompt)
                        if response:
                            st.session_state.mode_state["da_summary_result"] = response
                            log_query_event("Generar Resumen Ejecutivo IA", mode=c.MODE_DATA_ANALYSIS)
                            st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    # --- SUB-MODO: ANÁLISIS RÁPIDO ---
    if sub_modo == "Análisis Rápido":
        st.header("Análisis Rápido")
        context_buffer = io.StringIO() 
        st.subheader("Columnas Numéricas")
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        col_to_num = st.selectbox("Selecciona columna numérica:", numeric_cols, key="num_select")
        if col_to_num:
            c1, c2, c3 = st.columns(3)
            c1.metric("Media", f"{df[col_to_num].mean():.2f}")
            c2.metric("Mediana", f"{df[col_to_num].median():.2f}")
            c3.metric("Moda", str(df[col_to_num].mode().tolist()))
            context_buffer.write(f"Columna '{col_to_num}': Media={df[col_to_num].mean():.2f}\n")

        st.subheader("Columnas Categóricas")
        cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        col_to_cat = st.selectbox("Selecciona columna categórica:", cat_cols, key="cat_select")
        if col_to_cat:
            counts = df[col_to_cat].value_counts()
            percentages = df[col_to_cat].value_counts(normalize=True)
            df_freq = pd.DataFrame({'Conteo': counts, 'Porcentaje (%)': percentages.apply(lambda x: f"{x*100:.1f}%")})
            st.dataframe(df_freq, width='stretch')
            st.bar_chart(counts)
            st.session_state.mode_state["da_freq_table"] = df_freq 
            context_buffer.write(f"Distribución '{col_to_cat}':\n{df_freq.to_string()}\n")

        st.session_state.mode_state["data_analysis_stats_context"] = context_buffer.getvalue()

    # --- SUB-MODO: TABLA DINÁMICA ---
    if sub_modo == "Tabla Dinámica":
        st.header("Generador de Tabla Dinámica")
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        numeric_cols_pivot = df.select_dtypes(include=['number']).columns.tolist()
        
        c1, c2 = st.columns(2)
        index_col = c1.selectbox("Filas (Index)", all_cols, key="pivot_index")
        col_col = c2.selectbox("Columnas", all_cols, key="pivot_cols")
        val_col = c1.selectbox("Valores", numeric_cols_pivot, key="pivot_val")
        agg_func = c2.selectbox("Operación", ["count", "sum", "mean", "median"], key="pivot_agg")
        show_sig = st.checkbox("Calcular significancia (Chi-Squared)", key="pivot_sig", disabled=(agg_func != "count"))
        
        if index_col != "(Ninguno)" and val_col:
            try:
                pivot_raw = pd.pivot_table(df, values=val_col, index=index_col, 
                                          columns=col_col if col_col != "(Ninguno)" else None, 
                                          aggfunc=agg_func).fillna(0)
                st.session_state.mode_state["da_pivot_table"] = pivot_raw
                st.dataframe(pivot_raw.style.format("{:.1f}"), width='stretch')
                
                if show_sig and agg_func == 'count':
                    st.markdown("---")
                    if pivot_raw.size > 1:
                        chi2, p, dof, ex = stats.chi2_contingency(pivot_raw + 1) # +1 para evitar ceros
                        st.metric("P-Value (Chi-Squared)", f"{p:.4f}")
                        if p < 0.05:
                            st.success("✅ Significativo. Hay diferencias reales.")
                            residuals = (pivot_raw - ex) / np.sqrt(ex)
                            st.dataframe(residuals.style.applymap(style_residuals).format("{:.2f}"), width='stretch')
                        else: st.info("ℹ️ No significativo (Azar).")
                
                st.download_button("📥 Descargar Excel", data=to_excel(pivot_raw), file_name="pivot.xlsx")
            except Exception as e: st.error(f"Error: {e}")

    # --- SUB-MODO: NUBE DE PALABRAS ---
    if sub_modo == "Nube de Palabras":
        st.header("Nube de Palabras")
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        col_to_cloud = st.selectbox("Selecciona columna texto:", text_cols, key="cloud_select")
        
        if col_to_cloud:
            with st.spinner("Generando..."):
                text = " ".join(str(x) for x in df[col_to_cloud].dropna())
                if text:
                    wc = WordCloud(width=800, height=400, background_color='white', stopwords=get_stopwords()).generate(text)
                    fig, ax = plt.subplots(figsize=(10, 5))
                    ax.imshow(wc, interpolation='bilinear'); ax.axis('off')
                    st.pyplot(fig)
                    
                    img_stream = io.BytesIO()
                    fig.savefig(img_stream, format='png', bbox_inches='tight')
                    st.session_state.mode_state["da_wordcloud_fig"] = img_stream
                    
                    freqs = pd.DataFrame(list(wc.words_.items()), columns=['Palabra', 'Freq']).sort_values('Freq', ascending=False)
                    st.dataframe(freqs.head(20), width='stretch')

    # --- SUB-MODO: ANÁLISIS DE CORRELACIÓN ---
    if sub_modo == "Análisis de Correlación":
        st.header("Mapa de Calor de Correlación")
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        selected = st.multiselect("Selecciona columnas (min 2):", numeric_cols, default=numeric_cols[:5])
        
        if len(selected) >= 2:
            corr = df[selected].corr()
            fig, ax = plt.subplots()
            sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
            st.pyplot(fig)
            
            if st.button("Interpretar con IA"):
                with st.spinner("Interpretando..."):
                    resp = call_gemini_api(get_correlation_prompt(corr.to_string()))
                    st.session_state.mode_state["da_corr_interpretation"] = resp
            
            if "da_corr_interpretation" in st.session_state.mode_state:
                st.markdown(st.session_state.mode_state["da_corr_interpretation"])

    # --- SUB-MODO: COMPARACIÓN DE GRUPOS ---
    if sub_modo == "Comparación de Grupos":
        st.header("Comparación (T-Test / ANOVA)")
        num_cols = df.select_dtypes(include=['number']).columns.tolist()
        cat_cols = [c for c in df.columns if 2 <= df[c].nunique() <= 50]
        
        cat = st.selectbox("Grupos (Cat):", cat_cols)
        num = st.selectbox("Métrica (Num):", num_cols)
        
        if cat and num:
            groups = [df[num][df[cat] == g].dropna() for g in df[cat].unique()]
            if len(groups) >= 2:
                stat, p = stats.f_oneway(*groups) if len(groups) > 2 else stats.ttest_ind(groups[0], groups[1])
                st.metric("P-Value", f"{p:.4f}")
                
                if st.button("Interpretar"):
                    with st.spinner("Analizando..."):
                        resp = call_gemini_api(get_stat_test_prompt("ANOVA/T-Test", p, num, cat, len(groups)))
                        st.session_state.mode_state["da_stat_test_interpretation"] = resp
                
                if "da_stat_test_interpretation" in st.session_state.mode_state:
                    st.markdown(st.session_state.mode_state["da_stat_test_interpretation"])

    # --- SUB-MODO: EXPORTAR PPT ---
    if sub_modo == "Exportar a PPT":
        st.header("Exportar a PPT")
        if st.button("Generar .pptx", type="primary"):
            prs = Presentation("Plantilla_PPT_ATL.pptx") # Asegúrate de tener este archivo
            add_title_slide(prs, f"Análisis: {st.session_state.mode_state['da_selected_project_name']}")
            
            if "da_freq_table" in st.session_state.mode_state:
                add_table_slide(prs, "Frecuencias", st.session_state.mode_state["da_freq_table"])
            if "da_pivot_table" in st.session_state.mode_state:
                add_table_slide(prs, "Tabla Dinámica", st.session_state.mode_state["da_pivot_table"])
            if "da_wordcloud_fig" in st.session_state.mode_state:
                add_image_slide(prs, "Nube de Palabras", st.session_state.mode_state["da_wordcloud_fig"])
            
            out = io.BytesIO()
            prs.save(out)
            st.download_button("Descargar PPT", data=out.getvalue(), file_name="analisis.pptx")

    # --- SUB-MODO: AUTO-CODIFICACIÓN (SOLUCIÓN AL PROBLEMA JSON) ---
    if sub_modo == "Auto-Codificación":
        st.header("Auto-Codificación (Preguntas Abiertas)")
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if "da_autocode_results_df" in st.session_state.mode_state:
            st.dataframe(st.session_state.mode_state["da_autocode_results_df"], width='stretch')
            st.download_button("Descargar Excel", data=to_excel(st.session_state.mode_state["da_autocode_results_df"]), file_name="autocode.xlsx")
            if st.button("Analizar otra columna"):
                st.session_state.mode_state.pop("da_autocode_results_df", None); st.rerun()
        else:
            col_to_autocode = st.selectbox("Columna de texto:", text_cols)
            main_topic = st.text_input("Tema principal:", placeholder="Ej: Razones de compra")
            
            if st.button("Generar Categorías", type="primary"):
                if col_to_autocode and main_topic:
                    with st.spinner("Analizando con IA (esto toma unos segundos)..."):
                        try:
                            
                            # 1. Obtener muestra
                            sample = list(df[col_to_autocode].dropna().unique()[:100])
                            prompt = get_excel_autocode_prompt(main_topic, sample)
                            
                            # 2. Llamar a la API (AUMENTAMOS EL LÍMITE AQUÍ)
                            raw_response = call_gemini_api(
                                prompt,
                                generation_config_override={
                                    "response_mime_type": "application/json",
                                    "max_output_tokens": 8192 # <--- AUMENTADO (Antes era default o bajo)
                                }
                            )
                            
                            if not raw_response:
                                st.error("La IA no devolvió respuesta."); st.stop()

                            # 3. LIMPIEZA ROBUSTA DEL JSON (Aquí estaba el error antes)
                            cleaned_json_str = clean_gemini_json(raw_response)
                            categories = json.loads(cleaned_json_str) # Ahora es seguro

                            # 4. Contar menciones (Lógica Regex)
                            results = []
                            full_text = df[col_to_autocode].astype(str)
                            for cat in categories:
                                kw = [re.escape(k.strip()) for k in cat.get('keywords', []) if k.strip()]
                                if not kw: continue
                                pattern = r'\b(?:' + '|'.join(kw) + r')\b'
                                count = full_text.str.contains(pattern, case=False, regex=True).sum()
                                results.append({
                                    "Categoría": cat['categoria'],
                                    "Menciones": int(count),
                                    "Porcentaje (%)": (count / len(df)) * 100
                                })
                            
                            st.session_state.mode_state["da_autocode_results_df"] = pd.DataFrame(results).sort_values("Menciones", ascending=False)
                            st.rerun()

                        except json.JSONDecodeError:
                            st.error("Error: La IA devolvió un formato inválido incluso después de limpieza.")
                            st.code(raw_response)
                        except Exception as e:
                            st.error(f"Error: {e}")
                            st.code(traceback.format_exc())

def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.divider()
    user_id = st.session_state.user_id
    plan_limit = st.session_state.plan_features.get('project_upload_limit', 0)

    if "da_selected_project_id" in st.session_state.mode_state and "data_analysis_df" not in st.session_state.mode_state:
        with st.spinner("Cargando..."):
            df = load_project_data(st.session_state.mode_state["da_storage_path"])
            if df is not None: st.session_state.mode_state["data_analysis_df"] = df
            else: st.session_state.mode_state.pop("da_selected_project_id")

    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"], db, selected_files)
    else:
        with st.expander("➕ Crear Proyecto", expanded=True):
            show_project_creator(user_id, plan_limit)
        show_project_list(user_id)
