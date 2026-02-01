import streamlit as st
import pandas as pd
import io 
import json 
import traceback 

# --- Importaciones de Utils y Servicios ---
from utils import clean_gemini_json, render_process_status
from services.gemini_api import call_gemini_api
from services.supabase_db import supabase

# --- Componentes Refactorizados (Fase 3) ---
from components.project_manager import show_project_creator, show_project_list, PROJECT_BUCKET
from services.statistics import calculate_chi_squared, calculate_group_comparison, process_autocode_results
from services.plotting import generate_wordcloud_img, generate_correlation_heatmap
from reporting.ppt_generator import add_analysis_slide

# --- Prompts ---
from prompts import (
    get_excel_autocode_prompt, 
    get_correlation_prompt, get_stat_test_prompt 
)

# --- Librería PPTX ---
from pptx import Presentation
import constants as c

# =====================================================
# MODO: ANÁLISIS NUMÉRICO (EXCEL) - REFACTORIZADO
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

# --- FUNCIÓN PRINCIPAL DE ANÁLISIS ---

def show_project_analyzer(df):
    plan = st.session_state.plan_features
    sub_modo = st.session_state.mode_state.get("da_current_sub_mode", "Tabla Dinámica")
    
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    if st.button("← Volver a proyectos"): st.session_state.mode_state = {}; st.rerun()
    
    # --- MENÚ DE NAVEGACIÓN ---
    st.markdown("---")
    c1 = st.columns(3)
    if plan.get("da_has_pivot_table") and c1[0].button("Tablas Dinámicas", type="primary" if sub_modo=="Tabla Dinámica" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Tabla Dinámica"; st.rerun()
    if plan.get("da_has_autocode") and c1[1].button("Auto-Code", type="primary" if sub_modo=="Auto-Codificación" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Auto-Codificación"; st.rerun()
    if plan.get("da_has_wordcloud") and c1[2].button("Nube Palabras", type="primary" if sub_modo=="Nube de Palabras" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Nube de Palabras"; st.rerun()
    
    c2 = st.columns(3)
    if plan.get("da_has_correlation") and c2[0].button("Correlación", type="primary" if sub_modo=="Análisis de Correlación" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Análisis de Correlación"; st.rerun()
    if plan.get("da_has_group_comparison") and c2[1].button("Comparar Grupos", type="primary" if sub_modo=="Comparación de Grupos" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Comparación de Grupos"; st.rerun()
    if plan.get("da_has_ppt_export") and c2[2].button("Exportar PPT", type="primary" if sub_modo=="Exportar a PPT" else "secondary", width="stretch"): 
        st.session_state.mode_state["da_current_sub_mode"] = "Exportar a PPT"; st.rerun()

    st.divider()

    # --- SUB-MODO: TABLA DINÁMICA ---
    if sub_modo == "Tabla Dinámica":
        st.header("Tablas Dinámicas & Chi-Cuadrado")
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        idx = st.selectbox("Filas (Index):", all_cols)
        col = st.selectbox("Columnas:", all_cols)
        val = st.selectbox("Valores:", df.select_dtypes(include='number').columns)
        
        if idx != "(Ninguno)" and val:
            pivot = pd.pivot_table(df, values=val, index=idx, columns=col if col != "(Ninguno)" else None, aggfunc='count', fill_value=0)
            st.dataframe(pivot, width="stretch")
            st.session_state.mode_state["da_pivot_table"] = pivot 
            
            p, residuals = calculate_chi_squared(pivot)
            if p is not None:
                st.markdown("#### Test de Significancia (Chi²)")
                st.metric("P-Value", f"{p:.4f}", delta="Significativo" if p < 0.05 else "No significativo", delta_color="inverse")
                if p < 0.05:
                    st.caption("Los colores indican diferencias estadísticas.")
                    st.dataframe(residuals.style.applymap(style_residuals), width="stretch")

    # --- SUB-MODO: NUBE DE PALABRAS ---
    if sub_modo == "Nube de Palabras":
        st.header("Análisis Visual de Texto")
        col_text = st.selectbox("Columna de Texto:", df.select_dtypes(include=['object']).columns)
        if st.button("Generar Nube", type="primary"):
            with render_process_status("Generando visualización...", expanded=True) as status:
                text = " ".join(df[col_text].dropna().astype(str).tolist())
                img_buffer, freqs = generate_wordcloud_img(text)
                status.update(label="¡Listo!", state="complete", expanded=False)
                
            if img_buffer:
                st.image(img_buffer, use_column_width=True)
                st.session_state.mode_state["da_wordcloud_fig"] = img_buffer
                with st.expander("Ver tabla de frecuencias"):
                    st.dataframe(freqs.head(20), width="stretch")

    # --- SUB-MODO: CORRELACIÓN ---
    if sub_modo == "Análisis de Correlación":
        st.header("Mapa de Calor de Correlación")
        cols = st.multiselect("Selecciona columnas numéricas (min 2):", df.select_dtypes(include='number').columns)
        if len(cols) >= 2:
            fig, corr = generate_correlation_heatmap(df, cols)
            if fig:
                st.pyplot(fig)
                if st.button("Interpretar con IA"):
                    with render_process_status("Analizando correlaciones...", expanded=True) as status:
                        resp = call_gemini_api(get_correlation_prompt(corr.to_string()))
                        status.update(label="Interpretación Lista", state="complete", expanded=False)
                    st.markdown(resp)

    # --- SUB-MODO: COMPARACIÓN ---
    if sub_modo == "Comparación de Grupos":
        st.header("Pruebas de Hipótesis")
        num = st.selectbox("Variable Numérica:", df.select_dtypes(include='number').columns)
        cat = st.selectbox("Variable Categórica:", df.select_dtypes(include=['object', 'category']).columns)
        
        if st.button("Calcular Diferencias"):
            test_type, p, n_groups = calculate_group_comparison(df, num, cat)
            if test_type:
                st.info(f"Prueba realizada: **{test_type}** ({n_groups} grupos)")
                st.metric("P-Value", f"{p:.4f}", delta="Significativo" if p < 0.05 else "No significativo", delta_color="inverse")
                
                if st.button("Interpretar con IA"):
                     with render_process_status("Interpretando estadística...", expanded=True) as status:
                        resp = call_gemini_api(get_stat_test_prompt(test_type, p, num, cat, n_groups))
                        status.update(label="Listo", state="complete", expanded=False)
                     st.markdown(resp)

    # --- SUB-MODO: AUTO-CODIFICACIÓN (REFACTORIZADO) ---
    if sub_modo == "Auto-Codificación":
        st.header("Auto-Codificación con IA")
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if "da_autocode_results_df" in st.session_state.mode_state:
            st.success("✅ Resultados")
            st.dataframe(st.session_state.mode_state["da_autocode_results_df"], width="stretch")
            st.download_button("📥 Descargar Excel", data=to_excel(st.session_state.mode_state["da_autocode_results_df"]), file_name="autocode.xlsx")
            if st.button("Reiniciar"):
                st.session_state.mode_state.pop("da_autocode_results_df", None); st.rerun()
        else:
            col_to_autocode = st.selectbox("Columna a codificar:", text_cols)
            main_topic = st.text_input("Contexto / Tema Principal:", placeholder="Ej: Razones de insatisfacción")
            
            if st.button("Iniciar Auto-Codificación", type="primary"):
                if col_to_autocode and main_topic:
                    # PROCESO CON STATUS VISUAL
                    with render_process_status("Ejecutando proceso de codificación...", expanded=True) as status:
                        try:
                            # 1. IA Genera Categorías
                            status.write("🧠 Analizando muestra y definiendo categorías...")
                            sample = list(df[col_to_autocode].dropna().unique()[:80])
                            prompt = get_excel_autocode_prompt(main_topic, sample)
                            
                            raw_response = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json"})
                            if not raw_response: raise Exception("IA no respondió")
                            
                            categories = json.loads(clean_gemini_json(raw_response))
                            
                            # 2. Procesamiento Estadístico (Delegado a Servicio)
                            status.write("📊 Clasificando respuestas con Regex...")
                            results_df = process_autocode_results(df, col_to_autocode, categories)
                            
                            st.session_state.mode_state["da_autocode_results_df"] = results_df
                            status.update(label="¡Clasificación terminada!", state="complete", expanded=False)
                            st.rerun()
                            
                        except Exception as e:
                            status.update(label="Error", state="error")
                            st.error(f"Error: {e}")
                            st.code(traceback.format_exc())

    # --- SUB-MODO: EXPORTAR A PPT ---
    if sub_modo == "Exportar a PPT":
        st.header("Generar Reporte PowerPoint")
        
        if st.button("Generar .pptx", type="primary"):
            try:
                try: prs = Presentation("Plantilla_PPT_ATL.pptx")
                except: prs = Presentation()
                
                # Portada
                add_analysis_slide(prs, "title", f"Reporte: {st.session_state.mode_state['da_selected_project_name']}", None)
                
                # Slides condicionales usando el nuevo Helper
                if "da_pivot_table" in st.session_state.mode_state:
                    add_analysis_slide(prs, "table", "Cruce de Variables", st.session_state.mode_state["da_pivot_table"])
                    
                if "da_wordcloud_fig" in st.session_state.mode_state:
                    add_analysis_slide(prs, "image", "Análisis de Texto", st.session_state.mode_state["da_wordcloud_fig"])
                
                out = io.BytesIO()
                prs.save(out)
                st.download_button("Descargar Archivo", data=out.getvalue(), file_name=f"analisis.pptx")
                
            except Exception as e:
                st.error(f"Error generando PPT: {e}")

def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.divider()
    
    # 1. Cargar datos si hay proyecto seleccionado
    if "da_selected_project_id" in st.session_state.mode_state and "data_analysis_df" not in st.session_state.mode_state:
        with render_process_status("Cargando dataset...", expanded=True) as status:
            df = load_project_data(st.session_state.mode_state["da_storage_path"])
            status.update(label="Cargado", state="complete", expanded=False)
            
        if df is not None: 
            st.session_state.mode_state["data_analysis_df"] = df
        else: 
            st.session_state.mode_state.pop("da_selected_project_id", None)

    # 2. Router de Vistas
    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"])
    else:
        user_id = st.session_state.user_id
        limit = st.session_state.plan_features.get('project_upload_limit', 0)
        
        with st.expander("➕ Crear Nuevo Proyecto de Análisis", expanded=False):
            show_project_creator(user_id, limit)
        
        show_project_list(user_id)
