import streamlit as st
from utils import get_relevant_info, extract_text_from_pdfs
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from prompts import get_trend_analysis_prompt
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TENDENCIAS (MULTIFUENTE)
# =====================================================

def trend_analysis_mode(db_filtered, selected_files):
    st.subheader("Análisis de Tendencias")
    st.markdown("#### Función: Análisis Multifuente")
    st.markdown("""
    Identifica oportunidades estratégicas cruzando tres dimensiones de información:
    1. **Memoria Organizacional** (Tu repositorio seleccionado).
    2. **Información Nueva** (Archivos PDF que subas ahora).
    3. **Contexto de Mercado** (Perspectiva de fuentes públicas).
    """)

    # --- Sección de Resultados (Si ya existen) ---
    if "trend_result" in st.session_state.mode_state:
        st.divider()
        st.markdown(st.session_state.mode_state["trend_result"])
        
        col1, col2 = st.columns(2)
        with col1:
            # Generar PDF
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["trend_result"], 
                title=f"Tendencias - {st.session_state.mode_state.get('trend_topic', 'Análisis')}", 
                banner_path=banner_file
            )
            if pdf_bytes: 
                st.download_button(
                    label="Descargar Reporte PDF", 
                    data=pdf_bytes, 
                    file_name="analisis_tendencias.pdf", 
                    mime="application/pdf", 
                    width='stretch'
                )
        with col2:
            if st.button("Realizar Nuevo Análisis", width='stretch', type="secondary"):
                st.session_state.mode_state.pop("trend_result", None)
                st.session_state.mode_state.pop("trend_topic", None)
                st.rerun()
        return

    st.divider()

    # --- CONFIGURACIÓN DE FUENTES ---

    # 1. Repositorio (Ya viene filtrado desde el sidebar en app.py)
    st.info(f"📚 **Fuente 1: Repositorio.** Se utilizarán los {len(selected_files)} estudios filtrados en el menú lateral.")

    # 2. PDFs Cargados
    st.markdown("**📂 Fuente 2: Archivos PDF Externos** (Opcional)")
    uploaded_pdfs = st.file_uploader("Carga reportes de tendencias, papers o noticias:", type=["pdf"], accept_multiple_files=True)

    # 3. Fuentes Públicas
    st.markdown("**🌐 Fuente 3: Perspectiva de Fuentes Públicas**")
    public_options = [
        "DANE (Estadísticas Demográficas/Económicas)",
        "Banco de la República (Macroeconomía)",
        "Fenalco (Comercio)",
        "Camacol (Construcción/Vivienda)",
        "Euromonitor (Tendencias de Consumo Global)",
        "Google Trends (Interés de Búsqueda)",
        "McKinsey/Deloitte (Informes de Consultoría)",
        "Superintendencia de Industria y Comercio"
    ]
    selected_public_sources = st.multiselect(
        "Selecciona qué 'lentes' debe usar la IA para analizar el contexto:",
        options=public_options,
        help="La IA utilizará su conocimiento entrenado sobre estas entidades para enriquecer el análisis."
    )

    st.divider()

    # --- TEMA E INPUT ---
    trend_topic = st.text_area(
        "¿Qué tendencia o tema quieres analizar?", 
        placeholder="Ej: El impacto del trabajo híbrido en el consumo de alimentos fuera del hogar...",
        height=100
    )

    if st.button("Analizar Tendencia Multifuente", type="primary", width='stretch'):
        if not trend_topic.strip():
            st.warning("Por favor, define un tema para el análisis.")
            return

        with st.spinner("Triangulando información de Repositorio, PDFs y Fuentes Públicas..."):
            
            # A. Procesar Repositorio
            repo_text = get_relevant_info(db_filtered, trend_topic, selected_files)
            if not repo_text:
                repo_text = "No se encontró información relevante en el repositorio filtrado para este tema."

            # B. Procesar PDFs
            pdf_text = ""
            if uploaded_pdfs:
                try:
                    pdf_text = extract_text_from_pdfs(uploaded_pdfs)
                except Exception as e:
                    st.error(f"Error leyendo PDFs: {e}")
            else:
                pdf_text = "No se cargaron archivos PDF adicionales."

            # C. Construir Prompt
            final_prompt = get_trend_analysis_prompt(
                topic=trend_topic,
                repo_context=repo_text,
                pdf_context=pdf_text,
                public_sources_list=selected_public_sources
            )

            # D. Llamar a la IA (Streaming)
            stream = call_gemini_stream(final_prompt)
            
            if stream:
                st.markdown("---")
                response_container = st.empty()
                full_response = ""
                
                # Efecto visual de escritura
                for chunk in stream:
                    full_response += chunk
                    response_container.markdown(full_response + "▌")
                
                response_container.markdown(full_response)
                
                # Guardar estado
                st.session_state.mode_state["trend_result"] = full_response
                st.session_state.mode_state["trend_topic"] = trend_topic
                
                log_query_event(f"Trend Analysis: {trend_topic}", mode=c.MODE_TREND_ANALYSIS)
                st.rerun() # Para mostrar los botones de descarga limpios
            else:
                st.error("No se pudo generar el análisis.")
