import streamlit as st
import pandas as pd
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_survey_articulation_prompt
import constants as c
import io # Necesario para la descarga de Excel
import os # Necesario para chequear la plantilla

# --- Nuevas importaciones para Nube de Palabras ---
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import nltk

# --- Nuevas importaciones para PPTX ---
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

# --- Importaciones para Significancia ---
import scipy.stats as stats
import numpy as np

# =====================================================
# MODO: ANÁLISIS NUMÉRICO (EXCEL)
# =====================================================

@st.cache_data
def to_excel(df):
    """Función helper para convertir un DF a bytes de Excel en caché."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Pivot', index=True)
    return output.getvalue()

@st.cache_resource
def get_stopwords():
    """Descarga y cachea las stopwords en español de NLTK."""
    try:
        nltk.download('stopwords')
    except Exception as e:
        print(f"Error descargando stopwords de NLTK (se usarán las básicas): {e}")
    
    try:
        spanish_stopwords = nltk.corpus.stopwords.words('spanish')
    except:
        spanish_stopwords = ['de', 'la', 'el', 'en', 'y', 'a', 'los', 'del', 'las', 'un', 'para', 'con', 'no', 'una', 'su', 'que', 'se', 'por', 'es', 'más', 'lo', 'pero', 'me', 'mi', 'al', 'le', 'si', 'este', 'esta']
    
    custom_list = ['...', 'p', 'r', 'rta', 'respuesta', 'si', 'no', 'na', 'ninguno', 'ninguna', 'nan']
    spanish_stopwords.extend(custom_list)
    return set(spanish_stopwords)

# --- ¡NUEVA FUNCIÓN HELPER PARA ESTILOS! ---
def style_residuals(val):
    """Aplica color a los residuos estandarizados significativos."""
    if val > 1.96:
        return 'background-color: #d4edda; color: #155724' # Verde
    elif val < -1.96:
        return 'background-color: #f8d7da; color: #721c24' # Rojo
    else:
        return 'color: #333' # Negro (default)

# --- Funciones Helper para PPTX ---

def add_title_slide(prs, title_text):
    """Añade una diapositiva de título estándar."""
    try:
        slide_layout = prs.slide_layouts[0] 
        slide = prs.slides.add_slide(slide_layout)
        title = slide.shapes.title
        title.text = title_text
    except Exception as e:
        print(f"Error al añadir slide de título: {e}")

def add_image_slide(prs, title_text, image_stream):
    """Añade una diapositiva con un título y una imagen."""
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
    """Añade una diapositiva con un título y una tabla de pandas."""
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


def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS) # <-- Esto tomará el nuevo nombre
    st.markdown("Carga un archivo Excel (.xlsx) para realizar análisis numéricos (tablas dinámicas, frecuencias) y articularlos con el repositorio.") # <-- Texto modificado

    # --- 1. CARGADOR DE ARCHIVOS ---
    uploaded_file = st.file_uploader("Sube tu archivo .xlsx o .xls", type=["xlsx", "xls"], key="data_uploader")

    # Limpiar datos si no hay archivo
    if not uploaded_file:
        st.session_state.pop("data_analysis_df", None)
        st.session_state.pop("data_analysis_file_name", None)
        st.session_state.pop("data_analysis_chat_history", None)
        st.session_state.pop("data_analysis_stats_context", None)
        st.session_state.pop("da_freq_table", None)
        st.session_state.pop("da_pivot_table", None)
        st.session_state.pop("da_wordcloud_fig", None)

    # Procesar el archivo si se sube uno nuevo
    if uploaded_file:
        try:
            if "data_analysis_df" not in st.session_state or uploaded_file.name != st.session_state.get("data_analysis_file_name"):
                with st.spinner("Procesando archivo Excel..."):
                    st.session_state.data_analysis_df = pd.read_excel(uploaded_file)
                    st.session_state.data_analysis_file_name = uploaded_file.name
                    st.session_state.data_analysis_chat_history = [] 
                    st.session_state.data_analysis_stats_context = "" 
                    st.session_state.pop("da_freq_table", None)
                    st.session_state.pop("da_pivot_table", None)
                    st.session_state.pop("da_wordcloud_fig", None)
                st.success(f"Archivo '{uploaded_file.name}' cargado.")
        
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            st.session_state.pop("data_analysis_df", None)

    # --- 2. LÓGICA DE ANÁLISIS Y CHAT ---
    if "data_analysis_df" in st.session_state:
        df = st.session_state.data_analysis_df
        
        st.markdown(f"### Analizando: **{st.session_state.data_analysis_file_name}**")
        
        tab1, tab2, tab_cloud, tab_export, tab_chat = st.tabs([
            "Análisis Rápido", 
            "Tabla Dinámica", 
            "Nube de Palabras", 
            "Exportar a PPT",
            "Chat de Articulación"
        ])
        
        if "data_analysis_stats_context" not in st.session_state:
            st.session_state.data_analysis_stats_context = ""

        # --- PESTAÑA 1: ANÁLISIS RÁPIDO ---
        with tab1:
            st.header("Análisis Rápido")
            st.markdown("Calcula métricas clave de columnas individuales.")
            
            context_buffer = io.StringIO() 

            # A. Análisis de Tendencia Central (Numérico)
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

            # B. Análisis de Frecuencias (Categórico/Likert)
            st.subheader("Análisis de Columnas Categóricas (Likert, Región, etc.)")
            cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
            if not cat_cols:
                st.warning("El archivo no contiene columnas de texto/categoría para este análisis.")
            else:
                col_to_cat = st.selectbox("Selecciona una columna categórica:", cat_cols, key="cat_select")
                if col_to_cat:
                    counts = df[col_to_cat].value_counts()
                    percentages = df[col_to_cat].value_counts(normalize=True)
                    
                    df_freq = pd.DataFrame({
                        'Conteo': counts,
                        'Porcentaje (%)': percentages.apply(lambda x: f"{x*100:.1f}%")
                    })
                    
                    st.dataframe(df_freq, use_container_width=True)
                    st.bar_chart(counts)
                    
                    st.session_state.da_freq_table = df_freq 
                    
                    context_buffer.write(f"Distribución de la columna '{col_to_cat}':\n{df_freq.to_string()}\n\n")

            st.session_state.data_analysis_stats_context = context_buffer.getvalue()
            context_buffer.close()

        # --- PESTAÑA 2: TABLA DINÁMICA ---
        with tab2:
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

                display_mode = st.selectbox(
                    "Mostrar valores como:",
                    ["Valores Absolutos", "% del Total General", "% del Total de Fila", "% del Total de Columna"],
                    key="pivot_display"
                )
                
                show_sig = st.checkbox(
                    "Calcular significancia (Chi-Squared)", 
                    key="pivot_sig",
                    disabled=(agg_func != "count"), 
                    help="Calcula si las diferencias en la tabla son estadísticamente significativas. Solo funciona con la operación 'count'."
                )
                
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
                            
                            is_valid_shape = (pivot_df_raw.ndim == 1 and pivot_df_raw.shape[0] > 1) or \
                                             (pivot_df_raw.ndim == 2 and pivot_df_raw.shape[0] > 1 and pivot_df_raw.shape[1] > 1)
                            
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
                        st.download_button(
                            label="📥 Descargar Tabla como Excel",
                            data=excel_bytes,
                            file_name=f"pivot_table_{index_col}_{col_col}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"Error al crear la tabla: {e}")

        # --- PESTAÑA 3: NUBE de PALABRAS ---
        with tab_cloud:
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
                                wc = WordCloud(
                                    width=800, 
                                    height=400, 
                                    background_color='white',
                                    stopwords=stopwords,
                                    min_font_size=10,
                                    collocations=False 
                                )
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
                                    df_freq = pd.DataFrame(
                                        frequencies.items(), 
                                        columns=['Palabra', 'Frecuencia']
                                    ).sort_values(by='Frecuencia', ascending=False).reset_index(drop=True)
                                    
                                    st.dataframe(df_freq, use_container_width=True)
                                    
                                    st.session_state.da_freq_table_cloud = df_freq
                                    
                                    excel_bytes = to_excel(df_freq)
                                    st.download_button(
                                        label="📥 Descargar Frecuencias como Excel",
                                        data=excel_bytes,
                                        file_name=f"frecuencias_{col_to_cloud}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True
                                    )
                                    
                                    top_words = ', '.join(df_freq['Palabra'].head(10))
                                    st.session_state.data_analysis_stats_context += f"\nPalabras clave de '{col_to_cloud}': {top_words}...\n\n"
                                
                        except Exception as e:
                            st.error(f"Error al generar la nube de palabras: {e}")
                            st.error("Asegúrate de tener las librerías 'wordcloud' y 'matplotlib' instaladas.")
        
        # --- PESTAÑA 4: EXPORTAR A PPT ---
        with tab_export:
            st.header("Exportar a Presentación (.pptx)")
            st.markdown("Selecciona los análisis que has generado y descárgalos en una diapositiva de PowerPoint.")
            
            template_file = "Plantilla_PPT_ATL.pptx"
            if not os.path.isfile(template_file):
                st.error(f"Error: No se encontró el archivo de plantilla '{template_file}' en la carpeta raíz de la aplicación.")
                st.info("Asegúrate de que la plantilla base esté subida al repositorio de la app.")
            else:
                st.markdown("#### Seleccionar Contenido")
                
                include_freq = st.checkbox(
                    "Incluir Tabla de Frecuencias (de Pestaña 1)", 
                    value=True, 
                    disabled=not "da_freq_table" in st.session_state
                )
                include_pivot = st.checkbox(
                    "Incluir Tabla Dinámica (de Pestaña 2)", 
                    value=True, 
                    disabled=not "da_pivot_table" in st.session_state
                )
                include_cloud_img = st.checkbox(
                    "Incluir Nube de Palabras (Imagen)", 
                    value=True, 
                    disabled=not "da_wordcloud_fig" in st.session_state
                )
                include_cloud_table = st.checkbox(
                    "Incluir Tabla de Frecuencias (de Nube de Palabras)", 
                    value=False, 
                    disabled=not "da_freq_table_cloud" in st.session_state
                )
                
                if st.button("Generar Presentación", use_container_width=True, type="primary"):
                    with st.spinner("Creando archivo .pptx..."):
                        try:
                            prs = Presentation(template_file)
                            
                            add_title_slide(prs, f"Análisis de Datos: {st.session_state.data_analysis_file_name}")
                            
                            if include_freq and "da_freq_table" in st.session_state:
                                add_table_slide(prs, "Análisis de Frecuencias", st.session_state.da_freq_table)
                                
                            if include_pivot and "da_pivot_table" in st.session_state:
                                add_table_slide(prs, "Tabla Dinámica", st.session_state.da_pivot_table)
                                
                            if include_cloud_img and "da_wordcloud_fig" in st.session_state:
                                add_image_slide(prs, "Nube de Palabras", st.session_state.da_wordcloud_fig)
                            
                            if include_cloud_table and "da_freq_table_cloud" in st.session_state:
                                add_table_slide(prs, "Tabla de Frecuencias (Nube)", st.session_state.da_freq_table_cloud)

                            ppt_stream = io.BytesIO()
                            prs.save(ppt_stream)
                            ppt_stream.seek(0)
                            
                            st.session_state.generated_data_ppt = ppt_stream.getvalue()
                        
                        except Exception as e:
                            st.error(f"Error al generar la presentación: {e}")
                
                if "generated_data_ppt" in st.session_state:
                    st.download_button(
                        label="📥 Descargar Presentación (.pptx)",
                        data=st.session_state.generated_data_ppt,
                        file_name=f"analisis_{st.session_state.data_analysis_file_name}.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        use_container_width=True
                    )


        # --- PESTAÑA 5: CHAT DE ARTICULACIÓN ---
        with tab_chat:
            st.header("Chat de Articulación (Cuanti + Cuali)")
            
            if "data_analysis_chat_history" not in st.session_state:
                st.session_state.data_analysis_chat_history = []
                
            for msg in st.session_state.data_analysis_chat_history:
                with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
                    st.markdown(msg['message'])
            
            user_prompt = st.chat_input("Haz una pregunta sobre estos datos y el repositorio...")
            
            if user_prompt:
                st.session_state.data_analysis_chat_history.append({"role": "Usuario", "message": user_prompt})
                with st.chat_message("Usuario", avatar="👤"): 
                    st.markdown(user_prompt)
                
                with st.chat_message("Asistente", avatar="✨"):
                    message_placeholder = st.empty()
                    message_placeholder.markdown("Articulando...")
                    
                    survey_context = st.session_state.get("data_analysis_stats_context", "No hay datos de encuesta analizados.")
                    if not survey_context.strip():
                        survey_context = "El usuario está viendo los datos de la encuesta pero no ha seleccionado un análisis específico."
                    
                    repo_context = get_relevant_info(db, user_prompt, selected_files)
                    
                    conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.data_analysis_chat_history[-10:])

                    articulation_prompt = get_survey_articulation_prompt(
                        survey_context, 
                        repo_context, 
                        conversation_history
                    )
                    
                    response = call_gemini_api(articulation_prompt)
                    
                    if response: 
                        message_placeholder.markdown(response)
                        log_query_event(user_prompt, mode=c.MODE_DATA_ANALYSIS)
                        st.session_state.data_analysis_chat_history.append({
                            "role": "Asistente", 
                            "message": response
                        })
                    else: 
                        message_placeholder.error("Error al generar respuesta.")
                        st.session_state.data_analysis_chat_history.pop()