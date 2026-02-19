import streamlit as st
import pandas as pd
import io 
import json 
import traceback 

# --- Importaciones de Utils y Servicios ---
from utils import clean_gemini_json, render_process_status
from services.gemini_api import call_gemini_api
from services.supabase_db import supabase

# --- Componentes Refactorizados ---
from components.project_manager import show_project_creator, show_project_list, PROJECT_BUCKET
from services.statistics import calculate_chi_squared, calculate_group_comparison, process_autocode_results
from services.plotting import generate_wordcloud_img, generate_correlation_heatmap

# Manejo de error para generador de PPT
try:
    from reporting.ppt_generator import add_analysis_slide
    ppt_available = True
except ImportError:
    ppt_available = False

# --- Prompts ---
from prompts import (
    get_excel_autocode_prompt, 
    get_correlation_prompt, get_stat_test_prompt 
)

# --- Librería PPTX ---
try:
    from pptx import Presentation
except ImportError:
    pass

import constants as c

# =====================================================
# AUXILIARES DE ANÁLISIS
# =====================================================

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data', index=True)
    return output.getvalue()

def style_residuals(val):
    if val > 1.96: return 'background-color: #d4edda; color: #155724'
    elif val < -1.96: return 'background-color: #f8d7da; color: #721c24'
    else: return 'color: #333'

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

# =====================================================
# ANALIZADOR DE PROYECTOS
# =====================================================

def show_project_analyzer(df):
    plan = st.session_state.plan_features
    sub_modo = st.session_state.mode_state.get("da_current_sub_mode", "Tabla Dinámica")
    
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    if st.button("← Volver a proyectos"): 
        st.session_state.mode_state = {}
        st.rerun()
    
    st.markdown("---")
    # Menú de Navegación con use_container_width actualizado
    c1 = st.columns(3)
    if plan.get("da_has_pivot_table") and c1[0].button("Tablas Dinámicas", type="primary" if sub_modo=="Tabla Dinámica" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Tabla Dinámica"; st.rerun()
    if plan.get("da_has_autocode") and c1[1].button("Auto-Code", type="primary" if sub_modo=="Auto-Codificación" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Auto-Codificación"; st.rerun()
    if plan.get("da_has_wordcloud") and c1[2].button("Nube Palabras", type="primary" if sub_modo=="Nube de Palabras" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Nube de Palabras"; st.rerun()
    
    c2 = st.columns(3)
    if plan.get("da_has_correlation") and c2[0].button("Correlación", type="primary" if sub_modo=="Análisis de Correlación" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Análisis de Correlación"; st.rerun()
    if plan.get("da_has_group_comparison") and c2[1].button("Comparar Grupos", type="primary" if sub_modo=="Comparación de Grupos" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Comparación de Grupos"; st.rerun()
    if plan.get("da_has_ppt_export") and c2[2].button("Exportar PPT", type="primary" if sub_modo=="Exportar a PPT" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Exportar a PPT"; st.rerun()

    st.divider()

    # --- Lógica de Sub-modos (Tablas, Nubes, Correlación, etc.) ---
    if sub_modo == "Tabla Dinámica":
        st.header("Tablas Dinámicas & Chi-Cuadrado")
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        idx = st.selectbox("Filas (Index):", all_cols)
        col = st.selectbox("Columnas:", all_cols)
        val = st.selectbox("Valores:", df.select_dtypes(include='number').columns)
        
        if idx != "(Ninguno)" and val:
            pivot = pd.pivot_table(df, values=val, index=idx, columns=col if col != "(Ninguno)" else None, aggfunc='count', fill_value=0)
            st.dataframe(pivot, use_container_width=True)
            st.session_state.mode_state["da_pivot_table"] = pivot 
            
            p, residuals = calculate_chi_squared(pivot)
            if p is not None:
                st.markdown("#### Test de Significancia (Chi²)")
                st.metric("P-Value", f"{p:.4f}", delta="Significativo" if p < 0.05 else "No significativo", delta_color="inverse")
                if p < 0.05:
                    st.dataframe(residuals.style.applymap(style_residuals), use_container_width=True)

    # (El resto de los sub-modos mantienen su lógica interna original)
    # ...

# =====================================================
# FUNCIÓN PRINCIPAL (ENTRY POINT)
# =====================================================

def data_analysis_mode(db, selected_files):
    """
    Punto de entrada llamado desde app.py. 
    Maneja la carga de proyectos de Excel independientes del repositorio RAG.
    """
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.divider()
    
    # Carga de datos del proyecto seleccionado
    if "da_selected_project_id" in st.session_state.mode_state and "data_analysis_df" not in st.session_state.mode_state:
        with render_process_status("Cargando dataset...", expanded=True) as status:
            df = load_project_data(st.session_state.mode_state["da_storage_path"])
            status.update(label="Cargado", state="complete", expanded=False)
            
        if df is not None: 
            st.session_state.mode_state["data_analysis_df"] = df
        else: 
            st.session_state.mode_state.pop("da_selected_project_id", None)

    # Mostrar analizador o lista de proyectos
    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"])
    else:
        user_id = st.session_state.user_id
        limit = st.session_state.plan_features.get('project_upload_limit', 0)
        
        with st.expander("➕ Crear Nuevo Proyecto de Análisis", expanded=False):
            show_project_creator(user_id, limit)
        
        show_project_list(user_id)
