import streamlit as st
import pandas as pd
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_survey_articulation_prompt
import constants as c
import io # Necesario para la descarga de Excel

# =====================================================
# MODO: ANÁLISIS DE DATOS (EXCEL)
# =====================================================

@st.cache_data
def to_excel(df):
    """Función helper para convertir un DF a bytes de Excel en caché."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Pivot', index=True)
    return output.getvalue()

def data_analysis_mode(db, selected_files):
    st.subheader(c.MODE_DATA_ANALYSIS)
    st.markdown("Carga una base de datos (ventas, encuestas, etc.) para analizarla y articularla con el repositorio.")

    # --- 1. CARGADOR DE ARCHIVOS ---
    uploaded_file = st.file_uploader("Sube tu archivo .xlsx o .xls", type=["xlsx", "xls"], key="data_uploader")

    # Limpiar datos si no hay archivo
    if not uploaded_file:
        st.session_state.pop("data_analysis_df", None)
        st.session_state.pop("data_analysis_file_name", None)
        st.session_state.pop("data_analysis_chat_history", None)
        st.session_state.pop("data_analysis_stats_context", None)

    # Procesar el archivo si se sube uno nuevo
    if uploaded_file:
        try:
            if "data_analysis_df" not in st.session_state or uploaded_file.name != st.session_state.get("data_analysis_file_name"):
                with st.spinner("Procesando archivo Excel..."):
                    st.session_state.data_analysis_df = pd.read_excel(uploaded_file)
                    st.session_state.data_analysis_file_name = uploaded_file.name
                    st.session_state.data_analysis_chat_history = [] # Reiniciar chat
                    st.session_state.data_analysis_stats_context = "" # Reiniciar stats
                st.success(f"Archivo '{uploaded_file.name}' cargado.")
        
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            st.session_state.pop("data_analysis_df", None)

    # --- 2. LÓGICA DE ANÁLISIS Y CHAT ---
    # Todo el panel solo se muestra si tenemos un DataFrame cargado en memoria.
    
    if "data_analysis_df" in st.session_state:
        df = st.session_state.data_analysis_df
        
        st.markdown(f"### Analizando: **{st.session_state.data_analysis_file_name}**")
        
        tab1, tab2, tab3 = st.tabs(["Análisis Rápido", "Tabla Dinámica", "Chat de Articulación"])
        
        if "data_analysis_stats_context" not in st.session_state:
            st.session_state.data_analysis_stats_context = ""

        # --- PESTAÑA 1: ANÁLISIS RÁPIDO (Medias y Porcentajes) ---
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
                    
                    context_buffer.write(f"Distribución de la columna '{col_to_cat}':\n{df_freq.to_string()}\n\n")

            # Actualizar el contexto de la sesión
            st.session_state.data_analysis_stats_context = context_buffer.getvalue()
            context_buffer.close()

        # --- PESTAÑA 2: TABLA DINÁMICA (MODIFICADA) ---
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
                agg_func = c2.selectbox("Operación", ["sum", "count", "mean", "median", "min", "max"], key="pivot_agg")

                # --- INICIO DE LA MODIFICACIÓN (NUEVO DROPDOWN) ---
                display_mode = st.selectbox(
                    "Mostrar valores como:",
                    ["Valores Absolutos", "% del Total General", "% del Total de Fila", "% del Total de Columna"],
                    key="pivot_display"
                )
                # --- FIN DE LA MODIFICACIÓN ---

                # --- Lógica de Creación ---
                pivot_df_raw = None # Para guardar la tabla con números brutos
                
                try:
                    if index_col != "(Ninguno)" and col_col != "(Ninguno)":
                        pivot_df_raw = pd.pivot_table(df, values=val_col, index=index_col, columns=col_col, aggfunc=agg_func)
                    elif index_col != "(Ninguno)":
                        pivot_df_raw = pd.pivot_table(df, values=val_col, index=index_col, aggfunc=agg_func)
                    else:
                        st.info("Selecciona al menos una 'Fila (Index)' para generar una tabla.")
                        
                    # --- Si se generó una tabla, la mostramos y aplicamos % ---
                    if pivot_df_raw is not None:
                        pivot_df_raw = pivot_df_raw.fillna(0)
                        
                        # Guardar contexto para el chat (siempre los números brutos)
                        context_title = f"Tabla ({val_col} por {index_col})"
                        if col_col != "(Ninguno)": context_title += f"/{col_col}"
                        st.session_state.data_analysis_stats_context += f"\n{context_title}:\n{pivot_df_raw.to_string()}\n\n"

                        # --- Lógica de Visualización (Absolutos vs %) ---
                        st.markdown("#### Resultado de la Tabla Dinámica")
                        
                        display_df = pivot_df_raw.copy() # Copiamos para no modificar el original
                        
                        if display_mode == "% del Total General":
                            total_sum = display_df.sum().sum()
                            display_df = display_df / total_sum
                        elif display_mode == "% del Total de Fila":
                            display_df = display_df.apply(lambda x: x / x.sum(), axis=1)
                        elif display_mode == "% del Total de Columna":
                            display_df = display_df.apply(lambda x: x / x.sum(), axis=0)

                        # Formatear la tabla para mostrar
                        if display_mode == "Valores Absolutos":
                            st.dataframe(display_df.style.format("{:,.2f}"), use_container_width=True)
                        else:
                            st.dataframe(display_df.fillna(0).style.format("{:.1%}"), use_container_width=True)
                        
                        # --- Botón de Descarga (Siempre descarga los números brutos) ---
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


        # --- PESTAÑA 3: CHAT DE ARTICULACIÓN ---
        with tab3:
            st.header("Chat de Articulación (Cuanti + Cuali)")
            
            if "data_analysis_chat_history" not in st.session_state:
                st.session_state.data_analysis_chat_history = []
                
            # Mostrar historial de chat
            for msg in st.session_state.data_analysis_chat_history:
                with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
                    st.markdown(msg['message'])
            
            # Input del usuario
            user_prompt = st.chat_input("Haz una pregunta sobre estos datos y el repositorio...")
            
            if user_prompt:
                st.session_state.data_analysis_chat_history.append({"role": "Usuario", "message": user_prompt})
                with st.chat_message("Usuario", avatar="👤"): 
                    st.markdown(user_prompt)
                
                with st.chat_message("Asistente", avatar="✨"):
                    message_placeholder = st.empty()
                    message_placeholder.markdown("Articulando...")
                    
                    # 1. Obtener Contexto Cuantitativo (del Excel, Pestañas 1 y 2)
                    survey_context = st.session_state.get("data_analysis_stats_context", "No hay datos de encuesta analizados.")
                    if not survey_context.strip():
                        survey_context = "El usuario está viendo los datos de la encuesta pero no ha seleccionado un análisis específico."
                    
                    # 2. Obtener Contexto Cualitativo (del Repositorio S3)
                    repo_context = get_relevant_info(db, user_prompt, selected_files)
                    
                    # 3. Obtener Historial de este chat
                    conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.data_analysis_chat_history[-10:])

                    # 4. Crear el prompt articulado
                    articulation_prompt = get_survey_articulation_prompt(
                        survey_context, 
                        repo_context, 
                        conversation_history
                    )
                    
                    # 5. Llamar a la API
                    response = call_gemini_api(articulation_prompt)
                    
                    if response: 
                        message_placeholder.markdown(response)
                        # Loggear el evento
                        log_query_event(user_prompt, mode=c.MODE_DATA_ANALYSIS)
                        st.session_state.data_analysis_chat_history.append({
                            "role": "Asistente", 
                            "message": response
                        })
                    else: 
                        message_placeholder.error("Error al generar respuesta.")
                        st.session_state.data_analysis_chat_history.pop() # Eliminar el prompt fallido