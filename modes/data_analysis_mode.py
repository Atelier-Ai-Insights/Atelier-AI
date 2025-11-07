import streamlit as st
import pandas as pd
from utils import get_relevant_info, get_stopwords
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event, supabase
# --- INICIO DE MODIFICACIÓN DE IMPORTACIONES ---
from prompts import get_survey_articulation_prompt, get_excel_autocode_prompt # <-- Importamos el nuevo prompt
import constants as c
import io 
import os 
import uuid 
from datetime import datetime
import re # <-- ¡NUEVA IMPORTACIÓN!
import json # <-- ¡NUEVA IMPORTACIÓN!
import traceback # <-- ¡NUEVA IMPORTACIÓN!
# --- FIN DE MODIFICACIÓN DE IMPORTACIONES ---


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

# --- Funciones de Gestión de Proyectos (sin cambios) ---

@st.cache_data(ttl=600)
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

    if project_count >= plan_limit:
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
                    "user_id": user_id,
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
                    st.session_state.da_selected_project_id = proj_id
                    st.session_state.da_selected_project_name = proj_name
                    st.session_state.da_storage_path = storage_path
                    st.session_state.da_current_sub_mode = "Análisis Rápido" # Iniciar en la primera pestaña
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

# --- INICIO DE LA FUNCIÓN MODIFICADA ---
def show_project_analyzer(df, db_filtered, selected_files):
    """
    Muestra la UI de análisis completa (ahora con Auto-Codificación)
    """
    
    # --- 1. Lógica de Navegación de Sub-Modo (sin cambios) ---
    def set_da_sub_mode(new_mode):
        st.session_state.da_current_sub_mode = new_mode

    if "da_current_sub_mode" not in st.session_state:
        st.session_state.da_current_sub_mode = "Análisis Rápido" # Default
    
    sub_modo = st.session_state.da_current_sub_mode
    
    st.markdown(f"### Analizando: **{st.session_state.da_selected_project_name}**")
    
    if st.button("← Volver a la lista de proyectos"):
        st.session_state.pop("data_analysis_df", None)
        st.session_state.pop("da_selected_project_id", None)
        st.session_state.pop("da_selected_project_name", None)
        st.session_state.pop("da_storage_path", None)
        st.session_state.pop("da_freq_table", None)
        st.session_state.pop("da_pivot_table", None)
        st.session_state.pop("da_wordcloud_fig", None)
        st.session_state.pop("da_freq_table_cloud", None)
        st.session_state.pop("da_current_sub_mode", None) # Limpiar el estado del sub-modo
        # --- (LIMPIEZA DE ESTADOS) ---
        st.session_state.pop("da_autocode_results_df", None) # <-- NUEVO
        st.session_state.pop("da_autocode_json", None) # <-- NUEVO
        st.session_state.pop("data_analysis_chat_history", None) # <-- ELIMINADO (del modo anterior)
        st.rerun()
        
    # --- 2. Reemplazo de st.tabs por st.expander + st.button (MODIFICADO) ---
    
    with st.expander("Selecciona una función de análisis:", expanded=True):
        # --- (Modificamos la 5ta columna) ---
        col1, col2, col3, col4, col5 = st.columns(5) 
        with col1:
            st.button("Análisis Rápido", on_click=set_da_sub_mode, args=("Análisis Rápido",), use_container_width=True, type="primary" if sub_modo == "Análisis Rápido" else "secondary")
        with col2:
            st.button("Tabla Dinámica", on_click=set_da_sub_mode, args=("Tabla Dinámica",), use_container_width=True, type="primary" if sub_modo == "Tabla Dinámica" else "secondary")
        with col3:
            st.button("Nube de Palabras", on_click=set_da_sub_mode, args=("Nube de Palabras",), use_container_width=True, type="primary" if sub_modo == "Nube de Palabras" else "secondary")
        with col4:
            st.button("Exportar a PPT", on_click=set_da_sub_mode, args=("Exportar a PPT",), use_container_width=True, type="primary" if sub_modo == "Exportar a PPT" else "secondary")
        with col5:
            # --- (Este es el botón REEMPLAZADO) ---
            st.button("Auto-Codificación", on_click=set_da_sub_mode, args=("Auto-Codificación",), use_container_width=True, type="primary" if sub_modo == "Auto-Codificación" else "secondary")

    st.divider()
    
    # --- 3. Lógica condicional para mostrar el contenido ---

    if "data_analysis_stats_context" not in st.session_state:
        st.session_state.data_analysis_stats_context = ""
    
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
                st.session_state.da_freq_table = df_freq 
                context_buffer.write(f"Distribución de la columna '{col_to_cat}':\n{df_freq.to_string()}\n\n")

        st.session_state.data_analysis_stats_context = context_buffer.getvalue()
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
                    st.session_state.da_pivot_table = pivot_df_raw
                    context_title = f"Tabla ({val_col} por {index_col})"
                    if col_col != "(Ninguno)": context_title += f"/{col_col}"
                    st.session_state.data_analysis_stats_context += f"\n{context_title}:\n{pivot_df_raw.to_string()}\n\n"
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
                                st.session_state.da_wordcloud_fig = img_stream
                                st.subheader("Tabla de Frecuencias")
                                df_freq = pd.DataFrame(frequencies.items(), columns=['Palabra', 'Frecuencia']).sort_values(by='Frecuencia', ascending=False).reset_index(drop=True)
                                st.dataframe(df_freq, use_container_width=True)
                                st.session_state.da_freq_table_cloud = df_freq
                                excel_bytes = to_excel(df_freq)
                                st.download_button(label="📥 Descargar Frecuencias como Excel", data=excel_bytes, file_name=f"frecuencias_{col_to_cloud}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                                top_words = ', '.join(df_freq['Palabra'].head(10))
                                st.session_state.data_analysis_stats_context += f"\nPalabras clave de '{col_to_cloud}': {top_words}...\n\n"
                    except Exception as e:
                        st.error(f"Error al generar la nube de palabras: {e}")
    
    if sub_modo == "Exportar a PPT":
        st.header("Exportar a Presentación (.pptx)")
        st.markdown("Selecciona los análisis que has generado y descárgalos en una diapositiva de PowerPoint.")
        template_file = "Plantilla_PPT_ATL.pptx"
        if not os.path.isfile(template_file):
            st.error(f"Error: No se encontró el archivo de plantilla '{template_file}' en la carpeta raíz de la aplicación.")
            st.info("Asegúrate de que la plantilla base esté subida al repositorio de la app.")
        else:
            st.markdown("#### Seleccionar Contenido")
            include_freq = st.checkbox("Incluir Tabla de Frecuencias (de Pestaña 1)", value=True, disabled=not "da_freq_table" in st.session_state)
            include_pivot = st.checkbox("Incluir Tabla Dinámica (de Pestaña 2)", value=True, disabled=not "da_pivot_table" in st.session_state)
            include_cloud_img = st.checkbox("Incluir Nube de Palabras (Imagen)", value=True, disabled=not "da_wordcloud_fig" in st.session_state)
            include_cloud_table = st.checkbox("Incluir Tabla de Frecuencias (de Nube de Palabras)", value=False, disabled=not "da_freq_table_cloud" in st.session_state)
            
            # --- (¡NUEVA OPCIÓN DE EXPORTACIÓN!) ---
            include_autocode = st.checkbox("Incluir Tabla de Auto-Codificación (de Pestaña 5)", value=True, disabled=not "da_autocode_results_df" in st.session_state)
            
            if st.button("Generar Presentación", use_container_width=True, type="primary"):
                with st.spinner("Creando archivo .pptx..."):
                    try:
                        prs = Presentation(template_file)
                        add_title_slide(prs, f"Análisis de Datos: {st.session_state.da_selected_project_name}")
                        if include_freq and "da_freq_table" in st.session_state:
                            add_table_slide(prs, "Análisis de Frecuencias", st.session_state.da_freq_table)
                        if include_pivot and "da_pivot_table" in st.session_state:
                            add_table_slide(prs, "Tabla Dinámica", st.session_state.da_pivot_table)
                        if include_cloud_img and "da_wordcloud_fig" in st.session_state:
                            add_image_slide(prs, "Nube de Palabras", st.session_state.da_wordcloud_fig)
                        if include_cloud_table and "da_freq_table_cloud" in st.session_state:
                            add_table_slide(prs, "Tabla de Frecuencias (Nube)", st.session_state.da_freq_table_cloud)
                        
                        # --- (¡NUEVA LÓGICA DE EXPORTACIÓN!) ---
                        if include_autocode and "da_autocode_results_df" in st.session_state:
                            # Formatear el % antes de exportar
                            df_autocode_export = st.session_state.da_autocode_results_df.copy()
                            df_autocode_export["Porcentaje (%)"] = df_autocode_export["Porcentaje (%)"].apply(lambda x: f"{x:.1f}%")
                            add_table_slide(prs, "Auto-Codificación de Pregunta Abierta", df_autocode_export)
                        
                        ppt_stream = io.BytesIO()
                        prs.save(ppt_stream)
                        ppt_stream.seek(0)
                        st.session_state.generated_data_ppt = ppt_stream.getvalue()
                    except Exception as e:
                        st.error(f"Error al generar la presentación: {e}")
            if "generated_data_ppt" in st.session_state:
                st.download_button(label="📥 Descargar Presentación (.pptx)", data=st.session_state.generated_data_ppt, file_name=f"analisis_{st.session_state.da_selected_project_name}.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True)

    # --- ¡NUEVO BLOQUE: "Auto-Codificación"! ---
    if sub_modo == "Auto-Codificación":
        st.header("Auto-Codificación (Preguntas Abiertas)")
        st.markdown("""
        Esta herramienta utiliza IA para analizar una columna de texto (pregunta abierta) y 
        generar categorías de análisis (nodos). Luego, cuantifica cuántos participantes 
        mencionaron cada categoría.
        """)
        
        text_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if not text_cols:
            st.warning("El archivo no contiene columnas de texto/categoría para este análisis.")
        else:
            if "da_autocode_results_df" in st.session_state:
                st.subheader("Resultados de la Codificación")
                st.dataframe(
                    st.session_state.da_autocode_results_df,
                    column_config={
                        "Categoría": st.column_config.TextColumn(width="large"),
                        "Menciones (N)": st.column_config.NumberColumn(format="%d"),
                        "Porcentaje (%)": st.column_config.ProgressColumn(
                            format="%.1f%%",
                            min_value=0,
                            max_value=st.session_state.da_autocode_results_df["Porcentaje (%)"].max() if not st.session_state.da_autocode_results_df["Porcentaje (%)"].empty else 100
                        ),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                excel_bytes = to_excel(st.session_state.da_autocode_results_df)
                st.download_button(
                    label="📥 Descargar Tabla como Excel", 
                    data=excel_bytes, 
                    file_name="auto_codificacion.xlsx", 
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    use_container_width=True
                )

                if st.button("Analizar otra columna", use_container_width=True, type="secondary"):
                    st.session_state.pop("da_autocode_results_df", None)
                    st.session_state.pop("da_autocode_json", None)
                    st.rerun()
            
            else:
                col_to_autocode = st.selectbox("Selecciona la columna de texto (pregunta abierta):", text_cols, key="autocode_select")
                main_topic = st.text_input("¿Cuál es el tema principal de esta pregunta?", placeholder="Ej: 'Motivos de preferencia', 'Aspectos a mejorar'")
                
                if st.button("Generar Categorías y Conteo", use_container_width=True, type="primary"):
                    if not col_to_autocode or not main_topic:
                        st.warning("Por favor, selecciona una columna y define el tema principal.")
                    else:
                        with st.spinner("Analizando respuestas y generando categorías (IA)..."):
                            try:
                                # 1. Preparar datos de muestra para la IA
                                # Tomamos max 500 respuestas únicas no nulas como muestra
                                non_null_responses = df[col_to_autocode].dropna().unique()
                                if len(non_null_responses) == 0:
                                    st.error("La columna seleccionada está vacía o no tiene datos válidos."); return
                                
                                sample_list = list(non_null_responses[:500])
                                
                                # 2. Llamar a la IA para obtener el JSON de categorías y keywords
                                prompt = get_excel_autocode_prompt(main_topic, sample_list)
                                json_config = {"response_mime_type": "application/json"}
                                
                                # --- ¡INICIO DE LA CORRECCIÓN! ---
                                # Desactivamos los filtros de seguridad SÓLO para esta llamada,
                                # ya que a veces pueden truncar el JSON si detectan
                                # lenguaje "hostil" en las respuestas de los usuarios.
                                no_safety = [
                                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                                ]
                                
                                response_text = call_gemini_api(
                                    prompt,
                                    generation_config_override=json_config,
                                    safety_settings_override=no_safety # <-- Pasamos el override
                                )
                                # --- ¡FIN DE LA CORRECCIÓN! ---
                                
                                if not response_text:
                                    st.error("La IA no pudo generar una respuesta. Inténtalo de nuevo."); return

                                categories_json = json.loads(response_text)
                                st.session_state.da_autocode_json = categories_json
                                
                                # 3. Procesar el conteo en Python (más preciso)
                                total_participants = len(df) # El total de registros
                                full_series = df[col_to_autocode].astype(str) # La columna completa
                                results = []
                                
                                for cat in categories_json:
                                    category_name = cat.get('categoria', 'Sin Categoría')
                                    keywords = cat.get('keywords', [])
                                    
                                    if not keywords or not isinstance(keywords, list):
                                        continue
                                    
                                    # Creamos un patrón regex: \b(keyword1|keyword2|frase 3)\b
                                    # \b asegura que sean palabras completas
                                    # Filtramos keywords vacías antes de unirlas
                                    valid_keywords = [re.escape(k.strip()) for k in keywords if k.strip()]
                                    if not valid_keywords:
                                        continue
                                        
                                    regex_pattern = r'\b(' + '|'.join(valid_keywords) + r')\b'
                                    
                                    # Contamos cuántas filas contienen CUALQUIERA de las keywords
                                    mentions_count = full_series.str.contains(
                                        regex_pattern, 
                                        case=False, # Ignorar mayúsculas/minúsculas
                                        na=False,   # Tratar NaN como "no encontrado"
                                        regex=True
                                    ).sum()
                                    
                                    # Calculamos el porcentaje sobre el TOTAL de participantes
                                    percentage = (mentions_count / total_participants) * 100 if total_participants > 0 else 0
                                    
                                    results.append({
                                        "Categoría": category_name,
                                        "Menciones (N)": int(mentions_count),
                                        "Porcentaje (%)": percentage
                                    })

                                # 4. Guardar y mostrar resultados
                                if not results:
                                    st.warning("La IA generó categorías, pero no se encontraron menciones con esas keywords.")
                                else:
                                    df_results = pd.DataFrame(results).sort_values(by="Menciones (N)", ascending=False)
                                    st.session_state.da_autocode_results_df = df_results
                                    log_query_event(f"Auto-Codificación: {main_topic} ({col_to_autocode})", mode=c.MODE_DATA_ANALYSIS)
                                    st.rerun()

                            except json.JSONDecodeError:
                                st.error("Error de la IA: La respuesta no fue un JSON válido.")
                                st.code(response_text)
                            except re.error as e:
                                st.error(f"Error de Regex: La IA generó keywords inválidas. {e}")
                                st.code(st.session_state.get("da_autocode_json"))
                            except Exception as e:
                                st.error(f"Ocurrió un error inesperado: {e}")
                                st.code(traceback.format_exc())


# --- FUNCIÓN PRINCIPAL DEL MODO (NUEVA ARQUITECTURA) ---

def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.markdown("Carga, gestiona y analiza tus proyectos de datos (Excel). Articula tus hallazgos cuantitativos con el repositorio cualitativo.")
    st.divider()

    user_id = st.session_state.user_id
    plan_limit = st.session_state.plan_features.get('project_upload_limit', 0)

    # --- VISTA DE ANÁLISIS ---
    if "da_selected_project_id" in st.session_state and "data_analysis_df" not in st.session_state:
        with st.spinner("Cargando datos del proyecto..."):
            df = load_project_data(st.session_state.da_storage_path)
            if df is not None:
                st.session_state.data_analysis_df = df
            else:
                st.error("No se pudieron cargar los datos del proyecto.")
                st.session_state.pop("da_selected_project_id")
                st.session_state.pop("da_selected_project_name")
                st.session_state.pop("da_storage_path")

    if "data_analysis_df" in st.session_state:
        show_project_analyzer(st.session_state.data_analysis_df, db, selected_files)
    
    # --- VISTA DE GESTIÓN (PÁGINA PRINCIPAL) ---
    else:
        with st.expander("➕ Crear Nuevo Proyecto", expanded=True):
            show_project_creator(user_id, plan_limit)
        
        st.divider()
        
        show_project_list(user_id)