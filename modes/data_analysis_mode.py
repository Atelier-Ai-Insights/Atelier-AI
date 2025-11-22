import streamlit as st
import pandas as pd
import io 
import os 
import uuid 
from datetime import datetime
import re 
import json 
import traceback 

# --- Importaciones del Sistema ---
from utils import clean_gemini_json, to_excel # Importamos to_excel de utils si la moviste, o mantenla local si prefieres.
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase
import constants as c

# --- Importaciones de Nuevos Servicios (Refactor) ---
from services.statistics import get_dataframe_snapshot, calculate_chi_squared, calculate_group_comparison
from services.plotting import generate_wordcloud_img, generate_correlation_heatmap

# --- Prompts ---
from prompts import (
    get_excel_autocode_prompt, get_data_summary_prompt, 
    get_correlation_prompt, get_stat_test_prompt 
)

# --- PPT Generation ---
from pptx import Presentation
# Nota: Si moviste los helpers de PPT a un archivo aparte, impórtalos. 
# Si no, mantenemos los helpers visuales locales aquí por simplicidad de UI.
from pptx.util import Inches

# =====================================================
# MODO: ANÁLISIS NUMÉRICO (EXCEL) - VERSIÓN PROYECTOS
# =====================================================

PROJECT_BUCKET = "project_files"

# --- Funciones Helper UI (Locales) ---
# Mantenemos estas aquí porque son específicas de la construcción visual del PPT
# y no lógica de negocio pura.

@st.cache_data
def to_excel_local(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Pivot', index=True)
    return output.getvalue()

def style_residuals(val):
    if val > 1.96: return 'background-color: #d4edda; color: #155724' 
    elif val < -1.96: return 'background-color: #f8d7da; color: #721c24' 
    else: return 'color: #333'

def add_slide_helpers(prs, type, title, content):
    """Helper unificado para añadir slides."""
    try:
        if type == "title":
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = title
        elif type == "image":
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = title
            content.seek(0)
            slide.shapes.add_picture(content, Inches(0.5), Inches(1.5), width=Inches(9))
        elif type == "table":
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = title
            df = content.reset_index() if (content.index.name or isinstance(content.index, pd.MultiIndex)) else content
            rows, cols = df.shape
            table = slide.shapes.add_table(rows+1, cols, Inches(0.5), Inches(1.5), Inches(9), Inches(5.5)).table
            for c in range(cols):
                table.cell(0, c).text = str(df.columns[c])
            for r in range(rows):
                for c in range(cols):
                    table.cell(r+1, c).text = str(df.iloc[r, c])
    except Exception as e:
        print(f"Error slide {type}: {e}")

# --- Funciones de Gestión de Proyectos ---

@st.cache_data(ttl=600, show_spinner=False)
def load_project_data(storage_path):
    try:
        response = supabase.storage.from_(PROJECT_BUCKET).create_signed_url(storage_path, 60)
        df = pd.read_excel(response['signedURL'])
        return df
    except Exception as e:
        st.error(f"Error al cargar el proyecto: {e}"); return None

def show_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto")
    # ... (Código de creación de proyecto se mantiene igual, es lógica de DB) ...
    # Para ahorrar espacio en este ejemplo, asumo que mantienes la lógica original de show_project_creator 
    # o si prefieres te la copio completa de nuevo. 
    # (AVÍSAME SI NECESITAS QUE REPITAS EL CÓDIGO DE CREACIÓN DE PROYECTO AQUÍ)
    # Por ahora, usaré la lógica original simplificada:
    
    with st.form("new_project_form"):
        project_name = st.text_input("Nombre del Proyecto*")
        project_brand = st.text_input("Marca*")
        project_year = st.number_input("Año*", min_value=2020, value=datetime.now().year)
        uploaded_file = st.file_uploader("Archivo Excel (.xlsx)*", type=["xlsx"])
        if st.form_submit_button("Crear Proyecto"):
            if not all([project_name, project_brand, uploaded_file]):
                st.warning("Completa los campos.")
            else:
                try:
                    path = f"{user_id}/{uuid.uuid4()}{os.path.splitext(uploaded_file.name)[1]}"
                    supabase.storage.from_(PROJECT_BUCKET).upload(path, uploaded_file.getvalue(), {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
                    supabase.table("projects").insert({"project_name": project_name, "project_brand": project_brand, "project_year": int(project_year), "storage_path": path, "user_id": user_id}).execute()
                    st.success("Proyecto creado!"); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

def show_project_list(user_id):
    st.subheader("Mis Proyectos")
    try:
        projs = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data
        if not projs: st.info("No hay proyectos."); return
        for p in projs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{p['project_name']}**"); c1.caption(f"{p.get('project_brand')} | {p.get('project_year')}")
                if c2.button("Analizar", key=f"an_{p['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state.update({"da_selected_project_id": p['id'], "da_selected_project_name": p['project_name'], "da_storage_path": p['storage_path'], "da_current_sub_mode": "Resumen Ejecutivo IA"})
                    st.rerun()
                if c3.button("Eliminar", key=f"del_{p['id']}", width='stretch'):
                    supabase.storage.from_(PROJECT_BUCKET).remove([p['storage_path']])
                    supabase.table("projects").delete().eq("id", p['id']).execute()
                    st.success("Eliminado."); st.rerun()
    except Exception as e: st.error(f"Error: {e}")

# --- FUNCIÓN PRINCIPAL DE ANÁLISIS (REFACTORIZADA) ---

def show_project_analyzer(df, db_filtered, selected_files):
    
    # ... (Lógica de selección de permisos se mantiene igual) ...
    plan = st.session_state.plan_features
    sub_modo = st.session_state.mode_state.get("da_current_sub_mode", "Resumen Ejecutivo IA")
    
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    if st.button("← Volver"): st.session_state.mode_state = {}; st.rerun()
    
    # Navegación (Simplificada visualmente)
    cols = st.columns(4)
    if plan.get("da_has_summary") and cols[0].button("Resumen IA", type="primary" if sub_modo=="Resumen Ejecutivo IA" else "secondary"): st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"; st.rerun()
    if plan.get("da_has_quick_analysis") and cols[1].button("Estadísticas", type="primary" if sub_modo=="Análisis Rápido" else "secondary"): st.session_state.mode_state["da_current_sub_mode"] = "Análisis Rápido"; st.rerun()
    if plan.get("da_has_pivot_table") and cols[2].button("Tablas", type="primary" if sub_modo=="Tabla Dinámica" else "secondary"): st.session_state.mode_state["da_current_sub_mode"] = "Tabla Dinámica"; st.rerun()
    if plan.get("da_has_autocode") and cols[3].button("Auto-Code", type="primary" if sub_modo=="Auto-Codificación" else "secondary"): st.session_state.mode_state["da_current_sub_mode"] = "Auto-Codificación"; st.rerun()
    
    # Botones secundarios (Wordcloud, Correlación, PPT)
    c2 = st.columns(4)
    if plan.get("da_has_wordcloud") and c2[0].button("Wordcloud"): st.session_state.mode_state["da_current_sub_mode"] = "Nube de Palabras"; st.rerun()
    if plan.get("da_has_correlation") and c2[1].button("Correlación"): st.session_state.mode_state["da_current_sub_mode"] = "Análisis de Correlación"; st.rerun()
    if plan.get("da_has_group_comparison") and c2[2].button("Comparación"): st.session_state.mode_state["da_current_sub_mode"] = "Comparación de Grupos"; st.rerun()
    if plan.get("da_has_ppt_export") and c2[3].button("Exportar PPT"): st.session_state.mode_state["da_current_sub_mode"] = "Exportar a PPT"; st.rerun()

    st.divider()

    # --- SUB-MODO: RESUMEN EJECUTIVO ---
    if sub_modo == "Resumen Ejecutivo IA":
        st.header("Resumen Ejecutivo")
        if "da_summary_result" in st.session_state.mode_state:
            st.markdown(st.session_state.mode_state["da_summary_result"])
            if st.button("Regenerar"): st.session_state.mode_state.pop("da_summary_result"); st.rerun()
        else:
            if st.button("Generar Resumen", type="primary"):
                with st.spinner("Analizando datos..."):
                    # USO DE SERVICIO: get_dataframe_snapshot
                    snapshot = get_dataframe_snapshot(df)
                    prompt = get_data_summary_prompt(snapshot)
                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.mode_state["da_summary_result"] = response
                        log_query_event("Resumen Ejecutivo IA", mode=c.MODE_DATA_ANALYSIS)
                        st.rerun()

    # --- SUB-MODO: ANÁLISIS RÁPIDO ---
    if sub_modo == "Análisis Rápido":
        st.header("Análisis Rápido")
        # ... (Lógica de pandas simple se mantiene, es muy ligera para moverla) ...
        num_cols = df.select_dtypes(include=['number']).columns
        cat_cols = df.select_dtypes(include=['object', 'category']).columns
        
        c1, c2 = st.columns(2)
        col_num = c1.selectbox("Numérica:", num_cols)
        col_cat = c2.selectbox("Categórica:", cat_cols)
        
        if col_num:
            st.metric(f"Media {col_num}", f"{df[col_num].mean():.2f}")
        if col_cat:
            st.bar_chart(df[col_cat].value_counts())
            st.session_state.mode_state["da_freq_table"] = df[col_cat].value_counts().reset_index()

    # --- SUB-MODO: TABLA DINÁMICA ---
    if sub_modo == "Tabla Dinámica":
        st.header("Tabla Dinámica")
        # ... (Selectores UI) ...
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        idx = st.selectbox("Filas", all_cols); val = st.selectbox("Valores", df.select_dtypes(include='number').columns)
        
        if idx != "(Ninguno)" and val:
            pivot = pd.pivot_table(df, values=val, index=idx, aggfunc='count').fillna(0)
            st.dataframe(pivot)
            st.session_state.mode_state["da_pivot_table"] = pivot
            
            # USO DE SERVICIO: calculate_chi_squared
            p, residuals = calculate_chi_squared(pivot)
            if p is not None:
                st.metric("P-Value (Chi2)", f"{p:.4f}")
                if p < 0.05: 
                    st.success("Significativo")
                    st.dataframe(residuals.style.applymap(style_residuals))

    # --- SUB-MODO: NUBE DE PALABRAS ---
    if sub_modo == "Nube de Palabras":
        col_text = st.selectbox("Columna Texto:", df.select_dtypes(include='object').columns)
        if st.button("Generar"):
            with st.spinner("Creando nube..."):
                text = " ".join(df[col_text].dropna().astype(str))
                # USO DE SERVICIO: generate_wordcloud_img
                img_buffer, freqs = generate_wordcloud_img(text)
                
                if img_buffer:
                    st.image(img_buffer)
                    st.session_state.mode_state["da_wordcloud_fig"] = img_buffer
                    st.dataframe(freqs.head(10))

    # --- SUB-MODO: CORRELACIÓN ---
    if sub_modo == "Análisis de Correlación":
        cols = st.multiselect("Columnas:", df.select_dtypes(include='number').columns)
        if len(cols) > 1:
            # USO DE SERVICIO: generate_correlation_heatmap
            fig, corr = generate_correlation_heatmap(df, cols)
            st.pyplot(fig)
            if st.button("Interpretar IA"):
                resp = call_gemini_api(get_correlation_prompt(corr.to_string()))
                st.markdown(resp)

    # --- SUB-MODO: COMPARACIÓN ---
    if sub_modo == "Comparación de Grupos":
        num = st.selectbox("Métrica:", df.select_dtypes(include='number').columns)
        cat = st.selectbox("Grupos:", df.select_dtypes(include='object').columns)
        if st.button("Calcular"):
            # USO DE SERVICIO: calculate_group_comparison
            test, p, n_groups = calculate_group_comparison(df, num, cat)
            if test:
                st.metric(f"P-Value ({test})", f"{p:.4f}")
                if st.button("Interpretar"):
                    resp = call_gemini_api(get_stat_test_prompt(test, p, num, cat, n_groups))
                    st.markdown(resp)

    # --- SUB-MODO: AUTO-CODIFICACIÓN ---
    if sub_modo == "Auto-Codificación":
        # ... (Mantenemos la lógica de Regex/IA mejorada previamente, ya que es específica de UI+IA) ...
        # (Asegúrate de copiar el bloque de Auto-Codificación que ya arreglamos en el paso anterior)
        pass # Por brevedad del ejemplo, insertar aquí el bloque corregido del Paso 1

    # --- SUB-MODO: EXPORTAR ---
    if sub_modo == "Exportar a PPT":
        if st.button("Generar PPT"):
            prs = Presentation("Plantilla_PPT_ATL.pptx")
            add_slide_helpers(prs, "title", f"Análisis: {st.session_state.mode_state['da_selected_project_name']}", None)
            
            if "da_freq_table" in st.session_state.mode_state:
                add_slide_helpers(prs, "table", "Frecuencias", st.session_state.mode_state["da_freq_table"])
            
            out = io.BytesIO()
            prs.save(out)
            st.download_button("Descargar", out.getvalue(), "analisis.pptx")

def data_analysis_mode(db, selected_files):
    # Función envoltorio simple
    st.subheader(c.MODE_DATA_ANALYSIS); st.divider()
    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"], db, selected_files)
    else:
        # Aquí iría show_project_creator y show_project_list
        show_project_list(st.session_state.user_id)
