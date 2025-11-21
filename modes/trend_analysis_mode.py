import streamlit as st
from utils import get_relevant_info, extract_text_from_pdfs
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
# Importamos el diccionario SOURCE_LENSES para llenar el multiselect
from prompts import get_trend_analysis_prompt, SOURCE_LENSES 
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TENDENCIAS (MULTIFUENTE)
# =====================================================

def trend_analysis_mode(db_filtered, selected_files):
    st.subheader("Análisis de Tendencias")
    st.markdown("#### Función: Triangulación Estratégica")
    
    st.info(
        "Este módulo cruza tu **Data Interna** con **Lentes de Mercado Externos** "
        "para validar si tus hallazgos están alineados con la realidad nacional/global."
    )

    # --- Sección de Resultados ---
    if "trend_result" in st.session_state.mode_state:
        st.divider()
        st.markdown(st.session_state.mode_state["trend_result"])
        
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["trend_result"], 
                title=f"Tendencias - {st.session_state.mode_state.get('trend_topic', 'Análisis')}", 
                banner_path=banner_file
            )
            if pdf_bytes: 
                st.download_button("Descargar Reporte PDF", data=pdf_bytes, file_name="tendencias.pdf", mime="application/pdf", width='stretch')
        with col2:
            if st.button("Realizar Nuevo Análisis", width='stretch', type="secondary"):
                st.session_state.mode_state.pop("trend_result", None)
                st.rerun()
        return

    st.divider()

    # --- COLUMNAS DE FUENTES ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("#### 1. Data Interna")
        
        # --- NUEVA OPCIÓN: TOGGLE PARA REPOSITORIO ---
        use_repo = st.toggle("Incluir Repositorio (Memoria Histórica)", value=True)
        
        if use_repo:
            st.success(f"📚 **Repositorio Activo:** {len(selected_files)} estudios filtrados.")
        else:
            st.warning("⚠️ **Repositorio Desactivado:** El análisis se basará solo en PDFs y Fuentes Públicas.")
            
        uploaded_pdfs = st.file_uploader("📂 **Cargar PDFs Adicionales (Opcional):**", type=["pdf"], accept_multiple_files=True, help="Reports de tendencias, papers, noticias.")

    with c2:
        st.markdown("#### 2. Validación Externa (Lentes)")
        # Usamos las claves del diccionario que definimos en prompts.py
        public_options = list(SOURCE_LENSES.keys())
        
        selected_public_sources = st.multiselect(
            "Selecciona qué lentes aplicar para validar el mercado:",
            options=public_options,
            default=[public_options[0], public_options[5]], # DANE y Google Trends por defecto
            help="La IA usará su conocimiento de estas entidades para contrastar tus datos."
        )
        
        if selected_public_sources:
            st.caption(f"🔍 Se contrastará la información con indicadores de: {', '.join([s.split('(')[0] for s in selected_public_sources])}.")

    st.divider()

    # --- TEMA E INPUT ---
    trend_topic = st.text_area(
        "¿Qué hipótesis, categoría o tendencia quieres validar?", 
        placeholder="Ej: El aumento en el consumo de snacks saludables en estratos medios a pesar de la inflación...",
        height=100
    )

    if st.button("Ejecutar Triangulación de Fuentes", type="primary", width='stretch'):
        if not trend_topic.strip():
            st.warning("Por favor, define un tema para el análisis.")
            return

        # Usamos st.status para mostrar el progreso multifuente
        with st.status("Iniciando motor de inteligencia...", expanded=True) as status:
            
            # A. Procesar Repositorio (CONDICIONAL)
            repo_text = ""
            if use_repo:
                st.write("📚 Leyendo memoria organizacional (Repositorio)...")
                repo_text = get_relevant_info(db_filtered, trend_topic, selected_files)
                if not repo_text: repo_text = "Sin datos históricos relevantes en los archivos seleccionados."
            else:
                repo_text = "FUENTE OMITIDA POR EL USUARIO (No tener en cuenta el repositorio interno)."

            # B. Procesar PDFs
            st.write("📂 Procesando documentos cargados...")
            pdf_text = ""
            if uploaded_pdfs:
                try:
                    pdf_text = extract_text_from_pdfs(uploaded_pdfs)
                except Exception as e: st.error(f"Error PDFs: {e}")
            else: pdf_text = "Sin archivos externos adicionales."

            # C. Construir Prompt
            st.write("🌐 Conectando con lentes de conocimiento público...")
            final_prompt = get_trend_analysis_prompt(
                topic=trend_topic,
                repo_context=repo_text,
                pdf_context=pdf_text,
                public_sources_list=selected_public_sources
            )
            
            status.update(label="Triangulación completada. Generando reporte...", state="complete", expanded=False)

            # D. Llamar a la IA
            stream = call_gemini_stream(final_prompt)
            
            if stream:
                st.markdown("---")
                response_container = st.empty()
                full_response = ""
                
                for chunk in stream:
                    full_response += chunk
                    response_container.markdown(full_response + "▌")
                
                response_container.markdown(full_response)
                
                st.session_state.mode_state["trend_result"] = full_response
                st.session_state.mode_state["trend_topic"] = trend_topic
                
                log_query_event(f"Trend Analysis: {trend_topic}", mode=c.MODE_TREND_ANALYSIS)
                st.rerun()
            else:
                st.error("No se pudo generar el análisis.")
