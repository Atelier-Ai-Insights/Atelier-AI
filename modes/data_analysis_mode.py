import streamlit as st
import pandas as pd
from utils import get_relevant_info, get_stopwords
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


# --- Importaciones de Análisis ---
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

# --- Funciones Helper (sin cambios) ---

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

# --- Funciones de Gestión de Proyectos (show_project_creator MODIFICADA) ---

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

# --- ¡INICIO DE FUNCIÓN MODIFICADA! ---
def show_project_creator(user_id, plan_limit):
    st.subheader("Crear Nuevo Proyecto")
    
    try:
        response = supabase.table("projects").select("id", count='exact').eq("user_id", user_id).execute()
        project_count = response.count
    except Exception as e:
        st.error(f"Error al verificar el conteo de proyectos: {e}")
        return

    # --- ¡MODIFICADO! Leemos el límite de config.py ---
    # (plan_limit ya se pasa a esta función, la cual lee el nuevo valor de config.py)
    if project_count >= plan_limit and plan_limit != float('inf'):
        if plan_limit == 1:
            st.warning(f"Has alcanzado el límite de {int(plan_limit)} proyecto para tu plan actual. Deberás eliminar tu proyecto existente para crear uno nuevo.")
        else:
            st.warning(f"Has alcanzado el límite de {int(plan_limit)} proyectos para tu plan actual. Deberás eliminar un proyecto existente para crear uno nuevo.")
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
                    "storage_path": storage_path
                }
                
                supabase.table("projects").insert(project_data).execute()
                
                st.success(f"¡Proyecto '{project_name}' creado exitosamente!")
                st.rerun()

            except Exception as e:
                st.error(f"Error al crear el proyecto: {e}")
                try:
                    supabase.storage.from_(PROJECT_BUCKET).remove([storage_path])
                except:
                    pass
# --- ¡FIN DE FUNCIÓN MODIFICADA! ---

def show_project_list(user_id):
    st.subheader("Mis Proyectos")
    
    try:
        response = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        projects = response.data
    except Exception as e:
        st.error(f"Error al cargar la lista de proyectos: {e}")
        return

    if not projects:
        st.info("Aún no has creado ningún proyecto. Usa el formulario de arriba para empezar.")
        return

    for proj in projects:
        proj_id = proj['id']
        proj_name = proj['project_name']
        proj_brand = proj.get('project_brand', 'N/A')
        proj_year = proj.get('project_year', 'N/A')
        storage_path = proj['storage_path']
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.markdown(f"**{proj_name}**")
                st.caption(f"Marca: {proj_brand} | Año: {proj_year}")
            
            with col2:
                if st.button("Analizar", key=f"analizar_{proj_id}", use_container_width=True, type="primary"):
                    st.session_state.mode_state["da_selected_project_id"] = proj_id
                    st.session_state.mode_state["da_selected_project_name"] = proj_name
                    st.session_state.mode_state["da_storage_path"] = storage_path
                    st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
                    st.rerun()
            
            with col3:
                if st.button("Eliminar", key=f"eliminar_{proj_id}", use_container_width=True):
                    with st.spinner("Eliminando proyecto..."):
                        try:
                            supabase.storage.from_(PROJECT_BUCKET).remove([storage_path])
                            supabase.table("projects").delete().eq("id", proj_id).execute()
                            st.success(f"Proyecto '{proj_name}' eliminado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al eliminar: {e}")

# --- ¡INICIO DE FUNCIÓN MODIFICADA! ---
def show_project_analyzer(df, db_filtered, selected_files):
    """
    Muestra la UI de análisis completa (con 8 funciones)
    """
    
    # --- ¡NUEVO! Leemos los permisos del plan ---
    plan_features = st.session_state.plan_features
    
    # --- 1. Lógica de Navegación de Sub-Modo ---
    def set_da_sub_mode(new_mode):
        st.session_state.mode_state["da_current_sub_mode"] = new_mode

    if "da_current_sub_mode" not in st.session_state.mode_state:
        # Default al Resumen Ejecutivo (que todos los planes tienen)
        st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
    
    # --- ¡NUEVO! Control si el modo por defecto no está permitido ---
    # (Aunque en este caso, "Resumen Ejecutivo IA" sí está permitido para todos)
    current_default = st.session_state.mode_state["da_current_sub_mode"]
    
    if (current_default == "Resumen Ejecutivo IA" and not plan_features.get("da_has_summary")) or \
       (current_default == "Auto-Codificación" and not plan_features.get("da_has_autocode")) or \
       (current_default == "Nube de Palabras" and not plan_features.get("da_has_wordcloud")) or \
       (current_default == "Exportar a PPT" and not plan_features.get("da_has_ppt_export")) or \
       (current_default == "Análisis Rápido" and not plan_features.get("da_has_quick_analysis")) or \
       (current_default == "Tabla Dinámica" and not plan_features.get("da_has_pivot_table")) or \
       (current_default == "Análisis de Correlación" and not plan_features.get("da_has_correlation")) or \
       (current_default == "Comparación de Grupos" and not plan_features.get("da_has_group_comparison")):
           
           # Si el modo actual no está permitido, busca el primero que SÍ lo esté
           if plan_features.get("da_has_summary"):
               st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"
           elif plan_features.get("da_has_quick_analysis"):
               st.session_state.mode_state["da_current_sub_mode"] = "Análisis Rápido"
           else:
               # Si no hay ninguno (plan muy restrictivo), default a Resumen
               st.session_state.mode_state["da_current_sub_mode"] = "Resumen Ejecutivo IA"

    
    sub_modo = st.session_state.mode_state["da_current_sub_mode"]
    
    st.markdown(f"### Analizando: **{st.session_state.mode_state['da_selected_project_name']}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.mode_state = {}
        st.rerun()
        
    # --- 2. Layout de navegación (AHORA CONDICIONAL) ---
    
    st.markdown("##### Selecciona una función de análisis:")
    col_ia, col_stats = st.columns(2)

    with col_ia:
        with st.expander("📊 Funciones de IA Generativa", expanded=True):
            if plan_features.get("da_has_summary"):
                st.button("Resumen Ejecutivo", on_click=set_da_sub_mode, args=("Resumen Ejecutivo IA",), use_container_width=True, type="primary" if sub_modo == "Resumen Ejecutivo IA" else "secondary")
            if plan_features.get("da_has_autocode"):
                st.button("Auto-Codificación", on_click=set_da_sub_mode, args=("Auto-Codificación",), use_container_width=True, type="primary" if sub_modo == "Auto-Codificación" else "secondary")
            if plan_features.get("da_has_wordcloud"):
                st.button("Nube de Palabras", on_click=set_da_sub_mode, args=("Nube de Palabras",), use_container_width=True, type="primary" if sub_modo == "Nube de Palabras" else "secondary")
            if plan_features.get("da_has_ppt_export"):
                st.button("Exportar a PPT", on_click=set_da_sub_mode, args=("Exportar a PPT",), use_container_width=True, type="primary" if sub_modo == "Exportar a PPT" else "secondary")

    with col_stats:
        with st.expander("📈 Análisis Estadístico y Cruces", expanded=True):
            if plan_features.get("da_has_quick_analysis"):
                st.button("Análisis Rápido", on_click=set_da_sub_mode, args=("Análisis Rápido",), use_container_width=True, type="primary" if sub_modo == "Análisis Rápido" else "secondary")
            if plan_features.get("da_has_pivot_table"):
                st.button("Tabla Dinámica", on_click=set_da_sub_mode, args=("Tabla Dinámica",), use_container_width=True, type="primary" if sub_modo == "Tabla Dinámica" else "secondary")
            if plan_features.get("da_has_correlation"):
                st.button("Análisis de Correlación", on_click=set_da_sub_mode, args=("Análisis de Correlación",), use_container_width=True, type="primary" if sub_modo == "Análisis de Correlación" else "secondary")
            if plan_features.get("da_has_group_comparison"):
                st.button("Comparación de Grupos", on_click=set_da_sub_mode, args=("Comparación de Grupos",), use_container_width=True, type="primary" if sub_modo == "Comparación de Grupos" else "secondary")

    st.divider()
    
    # --- 3. Lógica condicional para mostrar el contenido (Sin cambios) ---
    # (El 'sub_modo' ya está filtrado por los botones, así que esta lógica
    # funcionará sin necesidad de más 'if plan_features...')

    if "data_analysis_stats_context" not in st.session_state.mode_state:
        st.session_state.mode_state["data_analysis_stats_context"] = ""
    
    if sub_modo == "Resumen Ejecutivo IA":
        st.header("Resumen Ejecutivo")
        st.markdown("Un primer vistazo a tus datos para identificar los hallazgos más evidentes y las hipótesis de exploración más interesantes.")

        if "da_summary_result" in st.session_state.mode_state:
            st.markdown(st.session_state.mode_state["da_summary_result"])
            if st.button("Generar nuevo resumen", use_container_width=True, type="secondary"):
                st.session_state.mode_state.pop("da_summary_result")
                st.rerun()
        else:
            if st.button("Generar Resumen Ejecutivo", use_container_width=True, type="primary"):
                with st.spinner("Analizando la estructura de los datos..."):
                    try:
                        snapshot_buffer = io.StringIO()
                        snapshot_buffer.write(f"Resumen del DataFrame (Total Filas: {len(df)})\n\n")
                        snapshot_buffer.write("### Columnas y Tipos de Datos:\n")
                        
                        df.info(buf=snapshot_buffer, verbose=False)
                        
                        snapshot_buffer.write("\n\n")

                        numeric_cols = df.select_dtypes(include=['number']).columns
                        if not numeric_cols.empty:
                            snapshot_buffer.write("### Resumen de Métricas Numéricas:\n")
                            snapshot_buffer.write(df[numeric_cols].describe().to_string(float_format="%.2f"))
                            snapshot_buffer.write("\n\n")
                        
                        cat_cols = df.select_dtypes(include=['object', 'category']).columns
                        if not cat_cols.empty:
                            snapshot_buffer.write("### Resumen de Distribución Categórica (Top 5):\n")
                            for col in cat_cols:
                                if df[col].nunique() < 50: 
                                    snapshot_buffer.write(f"\n**Columna: {col}**\n")
                                    snapshot_buffer.write(df[col].value_counts(normalize=True).head(5).to_string(float_format="%.1f%%"))
                                    snapshot_buffer.write("\n")
                        
                        data_snapshot = snapshot_buffer.getvalue()
                        snapshot_buffer.close()

                        prompt = get_data_summary_prompt(data_snapshot)
                        response = call_gemini_api(prompt)

                        if response:
                            st.session_state.mode_state["da_summary_result"] = response
                            log_query_event("Generar Resumen Ejecutivo IA", mode=c.MODE_DATA_ANALYSIS)
                            st.rerun()
                        else:
                            st.error("No se pudo generar el resumen.")

                    except Exception as e:
                        st.error(f"Error al generar el resumen: {e}")
                        st.code(traceback.format_exc())

    if sub_modo == "Análisis Rápido":
        st.header("Análisis Rápido")
        st.markdown("Calcula métricas clave de columnas individuales.")
        context_buffer = io.StringIO() 
        st.subheader("Análisis de Columnas Numéricas")
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if not numeric_cols:
            st.warning("El archivo no contiene columnas numéricas para este análisis.")
        else:
            col_to_num = st.selectbox("Selecciona una columna numérica:", numeric_cols, key="num_select")
            if col_to_num:
                mean_val = df[col_to_num].mean()
                median_val = df[col_to_num].median()
                mode_val = df[col_to_num].mode().tolist() 
                col1, col2, col3 = st.columns(3)
                col1.metric("Media", f"{mean_val:.2f}")
                col2.metric("Mediana", f"{median_val:.2f}")
                col3.metric("Moda(s)", ", ".join(map(str, mode_val)))
                context_buffer.write(f"Resumen de la columna '{col_to_num}':\n- Media: {mean_val:.2f}\n- Mediana: {median_val:.2f}\n- Moda(s): {', '.join(map(str, mode_val))}\n\n")

        st.subheader("Análisis de Columnas Categóricas (Likert, Región, etc.)")
        cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        if not cat_cols:
            st.warning("El archivo no contiene columnas de texto/categoría para este análisis.")
        else:
            col_to_cat = st.selectbox("Selecciona una columna categórica:", cat_cols, key="cat_select")
            if col_to_cat:
                counts = df[col_to_cat].value_counts()
                percentages = df[col_to_cat].value_counts(normalize=True)
                df_freq = pd.DataFrame({'Conteo': counts, 'Porcentaje (%)': percentages.apply(lambda x: f"{x*100:.1f}%")})
                st.dataframe(df_freq, use_container_width=True)
                st.bar_chart(counts)
                st.session_state.mode_state["da_freq_table"] = df_freq 
                context_buffer.write(f"Distribución de la columna '{col_to_cat}':\n{df_freq.to_string()}\n\n")

        st.session_state.mode_state["data_analysis_stats_context"] = context_buffer.getvalue()
        context_buffer.close()

    if sub_modo == "Tabla Dinámica":
        st.header("Generador de Tabla Dinámica")
        st.markdown("Crea tablas cruzadas para explorar relaciones entre variables.")
        all_cols = ["(Ninguno)"] + df.columns.tolist()
        numeric_cols_pivot = df.select_dtypes(include=['number']).columns.tolist()
        if not numeric_cols_pivot:
            st.error("No se pueden crear Tablas Dinámicas sin al menos una columna numérica (para 'Valores').")
        else:
            st.markdown("#### Configuración de la Tabla")
            c1, c2 = st.columns(2)
            index_col = c1.selectbox("Filas (Index)", all_cols, key="pivot_index")
            col_col = c2.selectbox("Columnas", all_cols, key="pivot_cols")
            val_col = c1.selectbox("Valores (Dato a calcular)", numeric_cols_pivot, key="pivot_val")
            agg_func = c2.selectbox("Operación", ["count", "sum", "mean", "median"], key="pivot_agg")
            display_mode = st.selectbox("Mostrar valores como:", ["Valores Absolutos", "% del Total General", "% del Total de Fila", "% del Total de Columna"], key="pivot_display")
            show_sig = st.checkbox("Calcular significancia (Chi-Squared)", key="pivot_sig", disabled=(agg_func != "count"), help="Solo funciona con la operación 'count'.")
            if agg_func != "count" and show_sig:
                st.warning("La significancia Chi-Squared solo se puede calcular con la operación 'count'.")
                show_sig = False
            pivot_df_raw = None 
            try:
                if index_col != "(Ninguno)" and col_col != "(Ninguno)":
                    pivot_df_raw = pd.pivot_table(df, values=val_col, index=index_col, columns=col_col, aggfunc=agg_func)
                elif index_col != "(Ninguno)":
                    pivot_df_raw = pd.pivot_table(df, values=val_col, index=index_col, aggfunc=agg_func)
                else:
                    st.info("Selecciona al menos una 'Fila (Index)' para generar una tabla.")
                if pivot_df_raw is not None:
                    pivot_df_raw = pivot_df_raw.fillna(0)
                    st.session_state.mode_state["da_pivot_table"] = pivot_df_raw
                    context_title = f"Tabla ({val_col} por {index_col})"
                    if col_col != "(Ninguno)": context_title += f"/{col_col}"
                    st.session_state.mode_state["data_analysis_stats_context"] += f"\n{context_title}:\n{pivot_df_raw.to_string()}\n\n"
                    st.markdown("#### Resultado de la Tabla Dinámica")
                    display_df = pivot_df_raw.copy() 
                    if display_mode == "% del Total General":
                        total_sum = display_df.sum().sum()
                        display_df = display_df / total_sum
                    elif display_mode == "% del Total de Fila":
                        display_df = display_df.apply(lambda x: x / x.sum(), axis=1)
                    elif display_mode == "% del Total de Columna":
                        display_df = display_df.apply(lambda x: x / x.sum(), axis=0)
                    if display_mode == "Valores Absolutos":
                        st.dataframe(display_df.style.format("{:,.2f}"), use_container_width=True)
                    else:
                        st.dataframe(display_df.fillna(0).style.format("{:.1%}"), use_container_width=True)
                    if show_sig and agg_func == 'count':
                        st.markdown("---")
                        st.subheader("Prueba de Significación (Chi-Squared)")
                        is_valid_shape = (pivot_df_raw.ndim == 1 and pivot_df_raw.shape[0] > 1) or (pivot_df_raw.ndim == 2 and pivot_df_raw.shape[0] > 1 and pivot_df_raw.shape[1] > 1)
                        if not is_valid_shape:
                            st.warning("La prueba Chi-Squared requiere al menos 2 filas (y 2 columnas si aplica).")
                        else:
                            try:
                                df_testable = pivot_df_raw + 1
                                chi2, p_value, dof, expected = stats.chi2_contingency(df_testable)
                                st.metric("Valor P (p-value)", f"{p_value:.4f}")
                                if p_value < 0.05:
                                    st.success("✅ **Resultado Significativo (p < 0.05)**. Las diferencias en la tabla son reales y no se deben al azar.")
                                    st.markdown("##### Análisis de Residuos (Celdas Significativas)")
                                    std_residuals = (df_testable - expected) / np.sqrt(expected)
                                    st.dataframe(std_residuals.style.applymap(style_residuals).format("{:.2f}"), use_container_width=True)
                                    st.caption("Verde (>1.96): Significativamente MÁS alto de lo esperado. Rojo (<-1.96): Significativamente MÁS BAJO de lo esperado.")
                                else:
                                    st.info("ℹ️ **Resultado No Significativo (p > 0.05)**. Las diferencias observadas en la tabla son probablemente producto del azar.")
                            except Exception as e:
                                st.error(f"Error al calcular Chi-Squared: {e}")
                    excel_bytes = to_excel(pivot_df_raw)
                    st.download_button(label="📥 Descargar Tabla como Excel", data=excel_bytes, file_name=f"pivot_table_{index_col}_{col_col}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e:
                st.error(f"Error al crear la tabla: {e}")

    if sub_modo == "Nube de Palabras":
        st.header("Nube de Palabras (Preguntas Abiertas)")
        st.markdown("Genera una nube de palabras a partir de una columna de texto.")
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        if not text_cols:
            st.warning("El archivo no contiene columnas de texto/categoría para este análisis.")
        else:
            col_to_cloud = st.selectbox("Selecciona una columna de texto:", text_cols, key="cloud_select")
            if col_to_cloud:
                with st.spinner("Generando nube de palabras y tabla..."):
                    try:
                        stopwords = get_stopwords()
                        text = " ".join(str(review) for review in df[col_to_cloud].dropna())
                        if not text.strip():
                            st.warning("La columna seleccionada está vacía o no contiene texto.")
                        else:
                            wc = WordCloud(width=800, height=400, background_color='white', stopwords=stopwords, min_font_size=10, collocations=False)
                            frequencies = wc.process_text(text)
                            if not frequencies:
                                st.warning("No se encontraron palabras para la nube (probablemente todas son 'stopwords').")
                            else:
                                wc.generate_from_frequencies(frequencies)
                                fig, ax = plt.subplots(figsize=(10, 5))
                                ax.imshow(wc, interpolation='bilinear')
                                ax.axis('off')
                                st.pyplot(fig)
                                img_stream = io.BytesIO()
                                fig.savefig(img_stream, format='png', bbox_inches='tight')
                                st.session_state.mode_state["da_wordcloud_fig"] = img_stream
                                st.subheader("Tabla de Frecuencias")
                                df_freq = pd.DataFrame(frequencies.items(), columns=['Palabra', 'Frecuencia']).sort_values(by='Frecuencia', ascending=False).reset_index(drop=True)
                                st.dataframe(df_freq, use_container_width=True)
                                st.session_state.mode_state["da_freq_table_cloud"] = df_freq
                                excel_bytes = to_excel(df_freq)
                                st.download_button(label="📥 Descargar Frecuencias como Excel", data=excel_bytes, file_name=f"frecuencias_{col_to_cloud}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                                top_words = ', '.join(df_freq['Palabra'].head(10))
                                st.session_state.mode_state["data_analysis_stats_context"] += f"\nPalabras clave de '{col_to_cloud}': {top_words}...\n\n"
                    except Exception as e:
                        st.error(f"Error al generar la nube de palabras: {e}")

    if sub_modo == "Análisis de Correlación":
        st.header("Análisis de Correlación (Heatmap)")
        st.markdown("Explora la relación entre diferentes variables numéricas (ej. Satisfacción vs. NPS).")
        
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        if len(numeric_cols) < 2:
            st.warning("Este análisis requiere al menos 2 columnas numéricas en tu archivo Excel.")
        else:
            selected_cols = st.multiselect("Selecciona 2 o más columnas numéricas para correlacionar:", numeric_cols, default=numeric_cols[:min(len(numeric_cols), 5)])
            
            if len(selected_cols) < 2:
                st.info("Por favor, selecciona al menos 2 columnas.")
            else:
                try:
                    corr_matrix = df[selected_cols].corr()
                    st.subheader("Mapa de Calor de Correlación")
                    fig, ax = plt.subplots()
                    sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
                    st.pyplot(fig)
                    
                    st.subheader("Interpretación de la IA")
                    if "da_corr_interpretation" in st.session_state.mode_state:
                        st.markdown(st.session_state.mode_state["da_corr_interpretation"])
                        if st.button("Generar nueva interpretación", key="new_corr_interp", type="secondary"):
                            st.session_state.mode_state.pop("da_corr_interpretation")
                            st.rerun()
                    else:
                        if st.button("Interpretar Correlaciones", type="primary"):
                            with st.spinner("Interpretando relaciones..."):
                                matrix_str = corr_matrix.to_string(float_format="%.2f")
                                prompt = get_correlation_prompt(matrix_str)
                                response = call_gemini_api(prompt)
                                if response:
                                    st.session_state.mode_state["da_corr_interpretation"] = response
                                    log_query_event(f"Interpretación Correlación: {', '.join(selected_cols)}", mode=c.MODE_DATA_ANALYSIS)
                                    st.rerun()
                                else:
                                    st.error("No se pudo generar la interpretación.")

                except Exception as e:
                    st.error(f"Error al calcular la correlación: {e}")
                    st.code(traceback.format_exc())

    if sub_modo == "Comparación de Grupos":
        st.header("Comparación de Grupos (T-Test / ANOVA)")
        st.markdown("Comprueba si existen diferencias estadísticamente significativas en una métrica numérica entre diferentes grupos categóricos.")

        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        cat_cols = [col for col in df.select_dtypes(include=['object', 'category']).columns if 2 <= df[col].nunique() <= 50] 

        if not numeric_cols or not cat_cols:
            st.warning("Este análisis requiere al menos una columna numérica (métrica) y una columna categórica (grupos).")
        else:
            st.markdown("#### Configuración de la Prueba")
            c1, c2 = st.columns(2)
            cat_col = c1.selectbox("Selecciona la Columna Categórica (Grupos):", cat_cols, help="La variable que define tus grupos (ej. 'Segmento', 'Género').")
            num_col = c2.selectbox("Selecciona la Columna Numérica (Métrica):", numeric_cols, help="La métrica que quieres comparar (ej. 'Satisfacción', 'Gasto').")
            
            if cat_col and num_col:
                try:
                    st.markdown("---")
                    st.subheader("Resultado de la Prueba")
                    
                    groups = df[cat_col].unique()
                    num_groups = len(groups)
                    group_data = [df[num_col][df[cat_col] == g].dropna() for g in groups]
                    
                    if num_groups == 2:
                        test_type = "Prueba T (T-Test)"
                        stat, p_value = stats.ttest_ind(group_data[0], group_data[1], nan_policy='omit')
                    elif num_groups > 2:
                        test_type = "ANOVA"
                        stat, p_value = stats.f_oneway(*group_data)
                    else:
                        st.error("La columna de grupos seleccionada solo tiene 1 valor."); return

                    col1, col2 = st.columns(2)
                    col1.metric("Prueba Realizada", test_type)
                    col2.metric("P-Value", f"{p_value:.4f}")

                    if "da_stat_test_interpretation" in st.session_state.mode_state:
                        st.markdown(st.session_state.mode_state["da_stat_test_interpretation"])
                        if st.button("Generar nueva interpretación", key="new_stat_interp", type="secondary"):
                            st.session_state.mode_state.pop("da_stat_test_interpretation")
                            st.rerun()
                    else:
                        if st.button("Interpretar Resultado", type="primary"):
                            with st.spinner("Interpretando P-Value..."):
                                prompt = get_stat_test_prompt(test_type, p_value, num_col, cat_col, num_groups)
                                response = call_gemini_api(prompt)
                                if response:
                                    st.session_state.mode_state["da_stat_test_interpretation"] = response
                                    log_query_event(f"Interpretación {test_type}: {num_col} vs {cat_col}", mode=c.MODE_DATA_ANALYSIS)
                                    st.rerun()
                                else:
                                    st.error("No se pudo generar la interpretación.")

                except Exception as e:
                    st.error(f"Error al ejecutar la prueba estadística: {e}")
                    st.code(traceback.format_exc())
    
    if sub_modo == "Exportar a PPT":
        st.header("Exportar a Presentación (.pptx)")
        st.markdown("Selecciona los análisis que has generado y descárgalos en una diapositiva de PowerPoint.")
        template_file = "Plantilla_PPT_ATL.pptx"
        if not os.path.isfile(template_file):
            st.error(f"Error: No se encontró el archivo de plantilla '{template_file}' en la carpeta raíz de la aplicación.")
            st.info("Asegúrate de que la plantilla base esté subida al repositorio de la app.")
        else:
            st.markdown("#### Seleccionar Contenido")
            include_freq = st.checkbox("Incluir Tabla de Frecuencias", value=True, disabled=not "da_freq_table" in st.session_state.mode_state)
            include_pivot = st.checkbox("Incluir Tabla Dinámica", value=True, disabled=not "da_pivot_table" in st.session_state.mode_state)
            include_cloud_img = st.checkbox("Incluir Nube de Palabras", value=True, disabled=not "da_wordcloud_fig" in st.session_state.mode_state)
            include_cloud_table = st.checkbox("Incluir Tabla de Frecuencias (de Nube de Palabras)", value=False, disabled=not "da_freq_table_cloud" in st.session_state.mode_state)
            
            include_autocode = st.checkbox("Incluir Tabla de Auto-Codificación", value=True, disabled=not "da_autocode_results_df" in st.session_state.mode_state)
            
            if st.button("Generar Presentación", use_container_width=True, type="primary"):
                with st.spinner("Creando archivo .pptx..."):
                    try:
                        prs = Presentation(template_file)
                        add_title_slide(prs, f"Análisis de Datos: {st.session_state.mode_state['da_selected_project_name']}")
                        if include_freq and "da_freq_table" in st.session_state.mode_state:
                            add_table_slide(prs, "Análisis de Frecuencias", st.session_state.mode_state["da_freq_table"])
                        if include_pivot and "da_pivot_table" in st.session_state.mode_state:
                            add_table_slide(prs, "Tabla Dinámica", st.session_state.mode_state["da_pivot_table"])
                        if include_cloud_img and "da_wordcloud_fig" in st.session_state.mode_state:
                            add_image_slide(prs, "Nube de Palabras", st.session_state.mode_state["da_wordcloud_fig"])
                        if include_cloud_table and "da_freq_table_cloud" in st.session_state.mode_state:
                            add_table_slide(prs, "Tabla de Frecuencias (Nube)", st.session_state.mode_state["da_freq_table_cloud"])
                        
                        if include_autocode and "da_autocode_results_df" in st.session_state.mode_state:
                            df_autocode_export = st.session_state.mode_state["da_autocode_results_df"].copy()
                            df_autocode_export["Porcentaje (%)"] = df_autocode_export["Porcentaje (%)"].apply(lambda x: f"{x:.1f}%")
                            add_table_slide(prs, "Auto-Codificación de Pregunta Abierta", df_autocode_export)
                        
                        ppt_stream = io.BytesIO()
                        prs.save(ppt_stream)
                        ppt_stream.seek(0)
                        st.session_state.mode_state["generated_data_ppt"] = ppt_stream.getvalue()
                    except Exception as e:
                        st.error(f"Error al generar la presentación: {e}")
            if "generated_data_ppt" in st.session_state.mode_state:
                st.download_button(label="📥 Descargar Presentación (.pptx)", data=st.session_state.mode_state["generated_data_ppt"], file_name=f"analisis_{st.session_state.mode_state['da_selected_project_name']}.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)

    if sub_modo == "Auto-Codificación":
        st.header("Auto-Codificación (Preguntas Abiertas)")
        st.markdown("""
        Esta herramienta utiliza IA para analizar una columna de texto (pregunta abierta) y 
        generar categorías de análisis. Luego, cuantifica cuántos participantes 
        mencionaron cada categoría.
        """)
        
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if not text_cols:
            st.warning("El archivo no contiene columnas de texto/categoría para este análisis.")
        else:
            if "da_autocode_results_df" in st.session_state.mode_state:
                st.subheader("Resultados de la Codificación")
                st.dataframe(
                    st.session_state.mode_state["da_autocode_results_df"],
                    column_config={
                        "Categoría": st.column_config.TextColumn(width="large"),
                        "Menciones (N)": st.column_config.NumberColumn(format="%d"),
                        "Porcentaje (%)": st.column_config.ProgressColumn(
                            format="%.1f%%",
                            min_value=0,
                            max_value=st.session_state.mode_state["da_autocode_results_df"]["Porcentaje (%)"].max() if not st.session_state.mode_state["da_autocode_results_df"]["Porcentaje (%)"].empty else 100
                        ),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                excel_bytes = to_excel(st.session_state.mode_state["da_autocode_results_df"])
                st.download_button(
                    label="📥 Descargar Tabla como Excel", 
                    data=excel_bytes, 
                    file_name="auto_codificacion.xlsx", 
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    use_container_width=True
                )

                if st.button("Analizar otra columna", use_container_width=True, type="secondary"):
                    st.session_state.mode_state.pop("da_autocode_results_df", None)
                    st.session_state.mode_state.pop("da_autocode_json", None)
                    st.session_state.mode_state.pop("da_autocode_selected_col", None)
                    st.rerun()
                
                st.divider()
                st.subheader("Explorar Verbatims por Categoría")
                
                categories_list = ["(Selecciona una categoría)"] + st.session_state.mode_state["da_autocode_results_df"]['Categoría'].tolist()
                selected_cat = st.selectbox("Selecciona una categoría para ver ejemplos:", categories_list, key="verbatim_select")

                if selected_cat != "(Selecciona una categoría)":
                    
                    if "da_autocode_selected_col" not in st.session_state.mode_state:
                        st.error("Error de estado: No se guardó la columna de origen. Por favor, haz clic en 'Analizar otra columna' y vuelve a generar el análisis.")
                    else:
                        try:
                            cat_json = next(item for item in st.session_state.mode_state["da_autocode_json"] if item["categoria"] == selected_cat)
                            keywords = cat_json.get("keywords", [])
                            
                            col_name = st.session_state.mode_state["da_autocode_selected_col"]
                            full_series = st.session_state.mode_state["data_analysis_df"][col_name].astype(str)

                            valid_keywords = [re.escape(k.strip()) for k in keywords if k.strip()]
                            if not valid_keywords:
                                st.warning("No se definieron keywords para esta categoría.")
                            else:
                                regex_pattern = r'\b(' + '|'.join(valid_keywords) + r')\b'
                                
                                matching_verbatims = full_series[
                                    full_series.str.contains(regex_pattern, case=False, na=False, regex=True)
                                ].dropna().unique() 

                                st.markdown(f"**Mostrando ejemplos de verbatims para '{selected_cat}':**")
                                if len(matching_verbatims) == 0:
                                    st.info("No se encontraron verbatims coincidentes (esto podría indicar un error si N > 0).")
                                else:
                                    for v in matching_verbatims[:20]:
                                        st.markdown(f"> {v}")
                                    
                                    if len(matching_verbatims) > 20:
                                        st.caption(f"...y {len(matching_verbatims) - 20} más. (Mostrando los primeros 20 ejemplos).")

                        except Exception as e:
                            st.error(f"Error al buscar verbatims: {e}")
            
            else:
                col_to_autocode = st.selectbox("Selecciona la columna de texto (pregunta abierta):", text_cols, key="autocode_select")
                main_topic = st.text_input("¿Cuál es el tema principal de esta pregunta?", placeholder="Ej: 'Motivos de preferencia', 'Aspectos a mejorar'")
                
                if st.button("Generar Categorías y Conteo", use_container_width=True, type="primary"):
                    if not col_to_autocode or not main_topic:
                        st.warning("Por favor, selecciona una columna y define el tema principal.")
                    else:
                        with st.spinner("Analizando respuestas y generando categorías (IA)..."):
                            try:
                                non_null_responses = df[col_to_autocode].dropna().unique()
                                if len(non_null_responses) == 0:
                                    st.error("La columna seleccionada está vacía o no tiene datos válidos."); return
                                
                                sample_list = list(non_null_responses[:100]) 
                                
                                prompt = get_excel_autocode_prompt(main_topic, sample_list)
                                json_config = {"response_mime_type": "application/json"}
                                no_safety = [
                                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                                ]
                                
                                response_text = call_gemini_api(
                                    prompt,
                                    generation_config_override=json_config,
                                    safety_settings_override=no_safety
                                )
                                
                                if not response_text:
                                    st.error("La IA no pudo generar una respuesta. Inténtalo de nuevo."); return

                                categories_json = json.loads(response_text)
                                st.session_state.mode_state["da_autocode_json"] = categories_json
                                st.session_state.mode_state["da_autocode_selected_col"] = col_to_autocode
                                
                                total_participants = len(df)
                                full_series = df[col_to_autocode].astype(str)
                                results = []
                                
                                for cat in categories_json:
                                    category_name = cat.get('categoria', 'Sin Categoría')
                                    keywords = cat.get('keywords', [])
                                    
                                    if not keywords or not isinstance(keywords, list):
                                        continue
                                    
                                    valid_keywords = [re.escape(k.strip()) for k in keywords if k.strip()]
                                    if not valid_keywords:
                                        continue
                                        
                                    regex_pattern = r'\b(' + '|'.join(valid_keywords) + r')\b'
                                    
                                    mentions_count = full_series.str.contains(
                                        regex_pattern, 
                                        case=False,
                                        na=False,
                                        regex=True
                                    ).sum()
                                    
                                    percentage = (mentions_count / total_participants) * 100 if total_participants > 0 else 0
                                    
                                    results.append({
                                        "Categoría": category_name,
                                        "Menciones (N)": int(mentions_count),
                                        "Porcentaje (%)": percentage
                                    })

                                if not results:
                                    st.warning("La IA generó categorías, pero no se encontraron menciones con esas keywords.")
                                else:
                                    df_results = pd.DataFrame(results).sort_values(by="Menciones (N)", ascending=False)
                                    st.session_state.mode_state["da_autocode_results_df"] = df_results
                                    log_query_event(f"Auto-Codificación: {main_topic} ({col_to_autocode})", mode=c.MODE_DATA_ANALYSIS)
                                    st.rerun()

                            except json.JSONDecodeError:
                                st.error("Error de la IA: La respuesta no fue un JSON válido.")
                                st.code(response_text)
                            except re.error as e:
                                st.error(f"Error de Regex: La IA generó keywords inválidas. {e}")
                                st.code(st.session_state.mode_state.get("da_autocode_json"))
                            except Exception as e:
                                st.error(f"Ocurrió un error inesperado: {e}")
                                st.code(traceback.format_exc())



def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.markdown("Carga, gestiona y analiza tus proyectos de datos (Excel). Articula tus hallazgos cuantitativos con el repositorio cualitativo.")
    st.divider()

    user_id = st.session_state.user_id
    # --- ¡MODIFICADO! Leemos el límite de proyectos del plan ---
    plan_limit = st.session_state.plan_features.get('project_upload_limit', 0)

    if "da_selected_project_id" in st.session_state.mode_state and "data_analysis_df" not in st.session_state.mode_state:
        with st.spinner("Cargando datos del proyecto..."):
            df = load_project_data(st.session_state.mode_state["da_storage_path"])
            if df is not None:
                st.session_state.mode_state["data_analysis_df"] = df
            else:
                st.error("No se pudieron cargar los datos del proyecto.")
                st.session_state.mode_state.pop("da_selected_project_id")
                st.session_state.mode_state.pop("da_selected_project_name")
                st.session_state.mode_state.pop("da_storage_path")

    if "data_analysis_df" in st.session_state.mode_state:
        show_project_analyzer(st.session_state.mode_state["data_analysis_df"], db, selected_files)
    
    else:
        with st.expander("➕ Crear Nuevo Proyecto", expanded=True):
            # --- ¡MODIFICADO! Pasamos el límite de proyectos numéricos
            show_project_creator(user_id, plan_limit)
        
        st.divider()
        
        show_project_list(user_id)
