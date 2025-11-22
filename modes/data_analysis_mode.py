import streamlit as st
import pandas as pd
import io 
import os 
import uuid 
from datetime import datetime
import re 
import json 
import traceback 

# --- Importaciones de Utils y Servicios Core ---
from utils import clean_gemini_json # Limpieza de JSON robusta
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase
import constants as c

# --- Importaciones de Nuevos Servicios de Refactorización ---
# (Asegúrate de haber creado estos archivos en la carpeta services/)
from services.statistics import get_dataframe_snapshot, calculate_chi_squared, calculate_group_comparison
from services.plotting import generate_wordcloud_img, generate_correlation_heatmap

# --- Prompts ---
from prompts import (
    get_excel_autocode_prompt, get_data_summary_prompt, 
    get_correlation_prompt, get_stat_test_prompt 
)

# --- Librería PPTX ---
from pptx import Presentation
from pptx.util import Inches

# =====================================================
# MODO: ANÁLISIS NUMÉRICO (EXCEL) - VERSIÓN PROYECTOS
# =====================================================

PROJECT_BUCKET = "project_files"

# --- Funciones Helper UI (Locales) ---

@st.cache_data
def to_excel(df):
    """Convierte un DataFrame a bytes de Excel para descarga."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data', index=True)
    return output.getvalue()

def style_residuals(val):
    """Estiliza celdas de pandas para resaltar residuos estandarizados significativos."""
    if val > 1.96: return 'background-color: #d4edda; color: #155724' # Verde (Más de lo esperado)
    elif val < -1.96: return 'background-color: #f8d7da; color: #721c24' # Rojo (Menos de lo esperado)
    else: return 'color: #333'

def add_slide_helpers(prs, type, title, content):
    """Helper unificado para añadir slides al PPT dependiendo del tipo de contenido."""
    try:
        if type == "title":
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = title
        
        elif type == "image":
            if content is None: return
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = title
            # Resetear puntero del buffer de imagen
            content.seek(0)
            slide.shapes.add_picture(content, Inches(0.5), Inches(1.5), width=Inches(9))
        
        elif type == "table":
            if content is None or content.empty: return
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = title
            
            # Aplanar índice si es MultiIndex para que se vea bien en PPT
            df = content.reset_index() if (content.index.name or isinstance(content.index, pd.MultiIndex)) else content
            
            rows, cols = df.shape
            # Limite de seguridad para PPT (evitar tablas gigantes que rompen el slide)
            if rows > 15: df = df.head(15); rows = 15
            
            graphic_frame = slide.shapes.add_table(rows+1, cols, Inches(0.5), Inches(1.5), Inches(9), Inches(5.5))
            table = graphic_frame.table
            
            # Headers
            for c in range(cols):
                table.cell(0, c).text = str(df.columns[c])
            # Body
            for r in range(rows):
                for c in range(cols):
                    val = df.iloc[r, c]
                    # Formato simple para números
                    table.cell(r+1, c).text = f"{val:.2f}" if isinstance(val, (float, int)) else str(val)
                    
    except Exception as e:
        print(f"Error generando slide tipo {type}: {e}")

# --- Funciones de Gestión de Proyectos (Carga/Creación) ---

@st.cache_data(ttl=600, show_spinner=False)
def load_project_data(storage_path):
    try:
        response = supabase.storage.from_(PROJECT_BUCKET).create_signed_url(storage_path, 60)
        signed_url = response['signedURL']
        # Soporte básico para Excel
        df = pd.read_excel(signed_url)
        return df
    except Exception as e:
        st.error(f"Error al cargar el proyecto: {e}")
        return None

def show_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto")
    
    # Validar límites
    try:
        response = supabase.table("projects").select("id", count='exact').eq("user_id", user_id).execute()
        if response.count >= plan_limit and plan_limit != float('inf'):
            st.warning(f"Límite de proyectos alcanzado ({int(plan_limit)}).")
            return
    except Exception as e: st.error(f"Error verificando límites: {e}"); return

    with st.form("new_project_form"):
        project_name = st.text_input("Nombre del Proyecto*", placeholder="Ej: Q1 Sales Tracking")
        project_brand = st.text_input("Marca*", placeholder="Ej: Brand X")
        project_year = st.number_input("Año*", min_value=2020, value=datetime.now().year)
        uploaded_file = st.file_uploader("Archivo Excel (.xlsx)*", type=["xlsx"])
        
        if st.form_submit_button("Crear Proyecto"):
            if not all([project_name, project_brand, uploaded_file]):
                st.warning("Completa los campos obligatorios.")
            else:
                with st.spinner("Subiendo archivo..."):
                    try:
                        file_ext = os.path.splitext(uploaded_file.name)[1]
                        path = f"{user_id}/{uuid.uuid4()}{file_ext}"
                        
                        supabase.storage.from_(PROJECT_BUCKET).upload(
                            path, 
                            uploaded_file.getvalue(), 
                            {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
                        )
                        
                        supabase.table("projects").insert({
                            "project_name": project_name, 
                            "project_brand": project_brand, 
                            "project_year": int(project_year), 
                            "storage_path": path, 
                            "user_id": user_id
                        }).execute()
                        
                        st.success("¡Proyecto creado!"); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

def show_project_list(user_id):
    st.subheader("Mis Proyectos")
    try:
        projs = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data
        if not projs: st.info("No hay proyectos creados."); return

        for p in projs:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(f"**{p['project_name']}**"); c1.caption(f"{p.get('project_brand')} | {p.get('project_year')}")
                
                if c2.button("Analizar", key=f"an_{p['id']}", width='stretch', type="primary"):
                    st.session_state.mode_state.update({
                        "da_selected_project_id": p['id'], 
                        "da_selected_project_name": p['project_name'], 
                        "da_storage_path": p['storage_path'],
                        "da_current_sub_mode": "Resumen Ejecutivo IA" # Reset submode
                    })
                    st.rerun()
                    
                if c3.button("Eliminar", key=f"del_{p['id']}", width='stretch'):
                    try:
                        supabase.storage.from_(PROJECT_BUCKET).remove([p['storage_path']])
                        supabase.table("projects").delete().eq("id", p['id']).execute()
                        st.success("Eliminado."); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
    except Exception as e: st.error(f"Error listando proyectos: {e}")

# --- FUNCIÓN PRINCIPAL DE ANÁLISIS (REFACTORIZADA) ---

def show_project_analyzer(df, db_filtered, selected_files):
    
    plan = st.session_state.plan_features
    sub_modo = st.session_state.mode_state.get("da_current_sub_mode", "Resumen Ejecutivo IA")
    
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    if st.button("← Volver a proyectos"): st.session_state.mode_state = {}; st.rerun()
    
    # --- MENÚ DE NAVEGACIÓN ---
    st.markdown("---")
    # Fila 1: IA y Estadísticas Básicas
    c1 = st.columns(4)
    if plan.get("da_has_summary") and c1[0].button("📝 Resumen IA", type="primary" if sub_modo=="Resumen Ejecutivo IA" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"; st.rerun()
        
    if plan.get("da_has_quick_analysis") and c1[1].button("⚡ Stats Rápidas", type="primary" if sub_modo=="Análisis Rápido" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Análisis Rápido"; st.rerun()
        
    if plan.get("da_has_pivot_table") and c1[2].button("🧮 Tablas Dinámicas", type="primary" if sub_modo=="Tabla Dinámica" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Tabla Dinámica"; st.rerun()
        
    if plan.get("da_has_autocode") and c1[3].button("🏷️ Auto-Code", type="primary" if sub_modo=="Auto-Codificación" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Auto-Codificación"; st.rerun()
    
    # Fila 2: Gráficos y Exportación
    c2 = st.columns(4)
    if plan.get("da_has_wordcloud") and c2[0].button("☁️ Nube Palabras", type="primary" if sub_modo=="Nube de Palabras" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Nube de Palabras"; st.rerun()
        
    if plan.get("da_has_correlation") and c2[1].button("🔥 Correlación", type="primary" if sub_modo=="Análisis de Correlación" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Análisis de Correlación"; st.rerun()
        
    if plan.get("da_has_group_comparison") and c2[2].button("🆚 Comparar Grupos", type="primary" if sub_modo=="Comparación de Grupos" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Comparación de Grupos"; st.rerun()
        
    if plan.get("da_has_ppt_export") and c2[3].button("💾 Exportar PPT", type="primary" if sub_modo=="Exportar a PPT" else "secondary", use_container_width=True): 
        st.session_state.mode_state["da_current_sub_mode"] = "Exportar a PPT"; st.rerun()

    st.divider()

    # --- SUB-MODO: RESUMEN EJECUTIVO IA ---
    if sub_modo == "Resumen Ejecutivo IA":
        st.header("Resumen Ejecutivo (IA)")
        if "da_summary_result" in st.session_state.mode_state:
            st.markdown(st.session_state.mode_state["da_summary_result"])
            if st.button("Regenerar Resumen", type="secondary", use_container_width=True): 
                st.session_state.mode_state.pop("da_summary_result"); st.rerun()
        else:
            if st.button("Generar Análisis", type="primary", use_container_width=True):
                with st.spinner("Analizando estructura de datos..."):
                    # REFACTOR: Uso de services/statistics
                    snapshot = get_dataframe_snapshot(df)
                    prompt = get_data_summary_prompt(snapshot)
                    response = call_gemini_api(prompt)
                    if response:
                        st.session_state.mode_state["da_summary_result"] = response
                        log_query_event("Resumen Ejecutivo IA", mode=c.MODE_DATA_ANALYSIS)
                        st.rerun()

    # --- SUB-MODO: ANÁLISIS RÁPIDO ---
    if sub_modo == "Análisis Rápido":
        st.header("Estadísticas Rápidas")
        c1, c2 = st.columns(2)
        col_num = c1.selectbox("Columna Numérica:", df.select_dtypes(include='number').columns)
        col_cat = c2.selectbox("Columna Categórica:", df.select_dtypes(include=['object', 'category']).columns)
        
        if col_num:
            metrics = df[col_num].describe()
            cols = st.columns(4)
            cols[0].metric("Media", f"{metrics['mean']:.2f}")
            cols[1].metric("Min", f"{metrics['min']:.2f}")
            cols[2].metric("Max", f"{metrics['max']:.2f}")
            cols[3].metric("Std", f"{metrics['std']:.2f}")
            
        if col_cat:
            counts = df[col_cat].value_counts().reset_index()
            counts.columns = ['Categoria', 'Conteo']
            st.bar_chart(counts.set_index('Categoria'))
            st.session_state.mode_state["da_freq_table"] = counts # Guardar para PPT

    # --- SUB-MODO: TABLA DINÁMICA ---
    if sub_modo == "Tabla Dinámica":
        st.header("Tablas Dinámicas & Chi-Cuadrado")
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        idx = st.selectbox("Filas (Index):", all_cols)
        col = st.selectbox("Columnas:", all_cols)
        val = st.selectbox("Valores:", df.select_dtypes(include='number').columns)
        
        if idx != "(Ninguno)" and val:
            pivot = pd.pivot_table(df, values=val, index=idx, columns=col if col != "(Ninguno)" else None, aggfunc='count', fill_value=0)
            st.dataframe(pivot, use_container_width=True)
            st.session_state.mode_state["da_pivot_table"] = pivot # Guardar para PPT
            
            # REFACTOR: Uso de services/statistics
            p, residuals = calculate_chi_squared(pivot)
            if p is not None:
                st.markdown("#### Test de Significancia (Chi²)")
                st.metric("P-Value", f"{p:.4f}", delta="Significativo" if p < 0.05 else "No significativo", delta_color="inverse")
                if p < 0.05:
                    st.caption("Los colores indican dónde hay más (verde) o menos (rojo) casos de lo esperado estadísticamente.")
                    st.dataframe(residuals.style.applymap(style_residuals), use_container_width=True)

    # --- SUB-MODO: NUBE DE PALABRAS ---
    if sub_modo == "Nube de Palabras":
        st.header("Análisis Visual de Texto")
        col_text = st.selectbox("Columna de Texto:", df.select_dtypes(include=['object']).columns)
        if st.button("Generar Nube", type="primary"):
            with st.spinner("Procesando texto..."):
                text = " ".join(df[col_text].dropna().astype(str).tolist())
                # REFACTOR: Uso de services/plotting
                img_buffer, freqs = generate_wordcloud_img(text)
                
                if img_buffer:
                    st.image(img_buffer, use_column_width=True)
                    st.session_state.mode_state["da_wordcloud_fig"] = img_buffer # Guardar para PPT
                    with st.expander("Ver tabla de frecuencias"):
                        st.dataframe(freqs.head(20), use_container_width=True)

    # --- SUB-MODO: CORRELACIÓN ---
    if sub_modo == "Análisis de Correlación":
        st.header("Mapa de Calor de Correlación")
        cols = st.multiselect("Selecciona columnas numéricas (min 2):", df.select_dtypes(include='number').columns)
        if len(cols) >= 2:
            # REFACTOR: Uso de services/plotting
            fig, corr = generate_correlation_heatmap(df, cols)
            if fig:
                st.pyplot(fig)
                if st.button("Interpretar con IA"):
                    with st.spinner("Interpretando..."):
                        resp = call_gemini_api(get_correlation_prompt(corr.to_string()))
                        st.markdown(resp)

    # --- SUB-MODO: COMPARACIÓN ---
    if sub_modo == "Comparación de Grupos":
        st.header("Pruebas de Hipótesis (T-Test / ANOVA)")
        num = st.selectbox("Variable Numérica (Métrica):", df.select_dtypes(include='number').columns)
        cat = st.selectbox("Variable Categórica (Grupos):", df.select_dtypes(include=['object', 'category']).columns)
        
        if st.button("Calcular Diferencias"):
            # REFACTOR: Uso de services/statistics
            test_type, p, n_groups = calculate_group_comparison(df, num, cat)
            if test_type:
                st.info(f"Prueba realizada: **{test_type}** ({n_groups} grupos detectados)")
                st.metric("P-Value", f"{p:.4f}", delta="Diferencias Reales" if p < 0.05 else "Diferencias por Azar", delta_color="inverse")
                
                if st.button("Interpretar hallazgo con IA"):
                     resp = call_gemini_api(get_stat_test_prompt(test_type, p, num, cat, n_groups))
                     st.markdown(resp)

    # --- SUB-MODO: AUTO-CODIFICACIÓN (ROBUSTA) ---
    if sub_modo == "Auto-Codificación":
        st.header("Auto-Codificación de Texto Abierto")
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if "da_autocode_results_df" in st.session_state.mode_state:
            st.success("✅ Codificación completada")
            st.dataframe(st.session_state.mode_state["da_autocode_results_df"], use_container_width=True)
            st.download_button("📥 Descargar Excel", data=to_excel(st.session_state.mode_state["da_autocode_results_df"]), file_name="autocode.xlsx")
            if st.button("Analizar otra columna"):
                st.session_state.mode_state.pop("da_autocode_results_df", None); st.rerun()
        else:
            col_to_autocode = st.selectbox("Columna a codificar:", text_cols)
            main_topic = st.text_input("Contexto / Tema Principal:", placeholder="Ej: Razones de insatisfacción")
            
            if st.button("Iniciar Auto-Codificación", type="primary"):
                if col_to_autocode and main_topic:
                    with st.spinner("1. Muestreando y generando categorías con IA..."):
                        try:
                            sample = list(df[col_to_autocode].dropna().unique()[:80]) # Muestra representativa
                            prompt = get_excel_autocode_prompt(main_topic, sample)
                            
                            # Llamada con parámetros ampliados
                            raw_response = call_gemini_api(prompt, generation_config_override={"response_mime_type": "application/json", "max_output_tokens": 8192})
                            
                            if not raw_response: raise Exception("IA no respondió")
                            
                            # LIMPIEZA ROBUSTA (Fix Priority 1.1)
                            cleaned_json = clean_gemini_json(raw_response)
                            categories = json.loads(cleaned_json)
                            
                            # Conteo Regex
                            results = []
                            full_text = df[col_to_autocode].astype(str)
                            total_rows = len(df)
                            
                            for cat in categories:
                                kw = [re.escape(k.strip()) for k in cat.get('keywords', []) if k.strip()]
                                if not kw: continue
                                pattern = r'\b(?:' + '|'.join(kw) + r')\b'
                                count = full_text.str.contains(pattern, case=False, regex=True).sum()
                                results.append({
                                    "Categoría": cat['categoria'],
                                    "Menciones": int(count),
                                    "%": round((count / total_rows) * 100, 1)
                                })
                            
                            st.session_state.mode_state["da_autocode_results_df"] = pd.DataFrame(results).sort_values("Menciones", ascending=False)
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Error en auto-codificación: {e}")
                            st.code(traceback.format_exc())

    # --- SUB-MODO: EXPORTAR A PPT ---
    if sub_modo == "Exportar a PPT":
        st.header("Generar Reporte PowerPoint")
        st.info("Se generará una presentación con los análisis que hayas realizado en esta sesión (Tablas, Nubes, etc).")
        
        if st.button("Generar .pptx", type="primary"):
            try:
                # Intentar cargar plantilla, sino crear en blanco
                try:
                    prs = Presentation("Plantilla_PPT_ATL.pptx")
                except:
                    prs = Presentation() # Fallback
                
                # Portada
                add_slide_helpers(prs, "title", f"Reporte: {st.session_state.mode_state['da_selected_project_name']}", None)
                
                # Slides condicionales (Solo si existen en session_state)
                if "da_freq_table" in st.session_state.mode_state:
                    add_slide_helpers(prs, "table", "Frecuencias", st.session_state.mode_state["da_freq_table"])
                    
                if "da_pivot_table" in st.session_state.mode_state:
                    add_slide_helpers(prs, "table", "Cruce de Variables", st.session_state.mode_state["da_pivot_table"])
                    
                if "da_wordcloud_fig" in st.session_state.mode_state:
                    add_slide_helpers(prs, "image", "Análisis de Texto", st.session_state.mode_state["da_wordcloud_fig"])
                
                # Guardar en buffer
                out = io.BytesIO()
                prs.save(out)
                st.download_button("📥 Descargar Archivo", data=out.getvalue(), file_name=f"analisis_{st.session_state.mode_state['da_selected_project_name']}.pptx")
                
            except Exception as e:
                st.error(f"Error generando PPT: {e}")

def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.divider()
    
    # 1. Cargar datos si hay proyecto seleccionado
    if "da_selected_project_id" in st.session_state.mode_state and "data_analysis_df" not in st.session_state.mode_state:
        with st.spinner("Cargando dataset del proyecto..."):
            df = load_project_data(st.session_state.mode_state["da_storage_path"])
            if df is not None: 
                st.session_state.mode_state["data_analysis_df"] = df
            else: 
                st.error("No se pudo cargar el archivo.")
                st.session_state.mode_state.pop("da_selected_project_id", None)

    # 2. Router de Vistas
    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"], db, selected_files)
    else:
        # Vista Inicial: Lista y Creador
        user_id = st.session_state.user_id
        limit = st.session_state.plan_features.get('project_upload_limit', 0)
        
        with st.expander("➕ Crear Nuevo Proyecto de Análisis", expanded=False):
            show_project_creator(user_id, limit)
        
        show_project_list(user_id)
