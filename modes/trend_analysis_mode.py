import streamlit as st
import pandas as pd
import altair as alt
import json
import fitz  # PyMuPDF para leer PDFs
# --- IMPORTACIONES ---
from utils import get_relevant_info, build_rag_context, clean_gemini_json
from services.gemini_api import call_gemini_stream, call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_trend_analysis_prompt, SOURCE_LENSES
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TENDENCIAS 2.0 (RAG + VISUAL)
# =====================================================

def trend_analysis_mode(db_filtered, selected_files):
    st.subheader("Análisis de Tendencias 2.0")
    st.markdown("#### Triangulación Estratégica & Matriz de Impacto")
    
    st.info("Este módulo cruza Data Interna + Evidencia Externa para validar oportunidades de mercado.")

    # --- SECCIÓN DE RESULTADOS ---
    if "trend_result" in st.session_state.mode_state:
        st.divider()
        
        # 1. VISUALIZACIÓN GRÁFICA (Altair)
        if "trend_chart_data" in st.session_state.mode_state:
            st.markdown("### 📊 Radar de Impacto")
            chart_data = st.session_state.mode_state["trend_chart_data"]
            
            # Gráfico de burbujas
            chart = alt.Chart(chart_data).mark_circle(size=200).encode(
                x=alt.X('Madurez:Q', title='Madurez de la Tendencia (1-10)', scale=alt.Scale(domain=[0, 11])),
                y=alt.Y('Impacto:Q', title='Impacto en el Negocio (1-10)', scale=alt.Scale(domain=[0, 11])),
                color='Categoria:N',
                tooltip=['Tendencia', 'Madurez', 'Impacto', 'Categoria'],
                size=alt.value(500)
            ).properties(
                title=f"Matriz de Oportunidades: {st.session_state.mode_state.get('trend_topic')}",
                height=350
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)

        # 2. REPORTE TEXTUAL
        st.markdown("### 📝 Análisis Detallado")
        st.markdown(st.session_state.mode_state["trend_result"])
        
        # 3. BOTONES DE ACCIÓN
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["trend_result"], 
                title=f"Tendencias - {st.session_state.mode_state.get('trend_topic', 'Análisis')}", 
                banner_path=banner_file
            )
            if pdf_bytes: 
                st.download_button("Descargar Reporte PDF", data=pdf_bytes, file_name="tendencias.pdf", mime="application/pdf", width='stretch', type="primary")
        with col2:
            if st.button("Realizar Nuevo Análisis", width='stretch', type="secondary"):
                # Limpiar estado específico de este modo
                keys_to_remove = ["trend_result", "trend_topic", "trend_chart_data"]
                for k in keys_to_remove: st.session_state.mode_state.pop(k, None)
                st.rerun()
        return

    # --- SECCIÓN DE CONFIGURACIÓN ---
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 1. Fuentes Internas")
        use_repo = st.toggle("Repositorio Histórico", value=True)
        uploaded_pdfs = st.file_uploader("Cargar PDFs Adicionales:", type=["pdf"], accept_multiple_files=True)

    with c2:
        st.markdown("#### 2. Lentes Externos")
        public_options = list(SOURCE_LENSES.keys())
        selected_public_sources = st.multiselect(
            "Perspectivas a aplicar:",
            options=public_options,
            default=[public_options[0], public_options[5]], # DANE y Google Trends por defecto
            help="La IA simulará el análisis desde estas perspectivas."
        )

    st.divider()
    trend_topic = st.text_area("Hipótesis o Tendencia a Validar:", height=100, placeholder="Ej: Crecimiento de bebidas vegetales en el segmento premium...")

    if st.button("Ejecutar Triangulación", type="primary", width='stretch'):
        if not trend_topic.strip():
            st.warning("Por favor, define un tema para el análisis."); return

        with st.status("🔍 Iniciando motor de tendencias...", expanded=True) as status:
            
            # A. PROCESAMIENTO INTELIGENTE (RAG SELECTIVO)
            status.write("🧠 Realizando minería de datos (Smart RAG)...")
            
            # 1. Extraer texto del Repositorio (si está activo)
            repo_docs = []
            if use_repo and db_filtered:
                for doc in db_filtered:
                    full_content = ""
                    # Concatenar contenido de los grupos del estudio
                    for grupo in doc.get("grupos", []):
                        full_content += str(grupo.get('contenido_texto', '')) + "\n"
                    
                    if full_content.strip():
                        repo_docs.append({'source': doc.get('nombre_archivo', 'Repo'), 'content': full_content})

            # 2. Extraer texto de PDFs subidos
            pdf_docs = []
            if uploaded_pdfs:
                for pdf in uploaded_pdfs:
                    try:
                        with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                            text = "".join([page.get_text() for page in doc])
                            if text.strip():
                                pdf_docs.append({'source': pdf.name, 'content': text})
                    except Exception as e:
                        print(f"Error leyendo PDF {pdf.name}: {e}")

            # 3. Aplicar RAG (Filtrado Semántico)
            # Unimos todo para buscar solo los párrafos relevantes al 'trend_topic'
            all_docs = repo_docs + pdf_docs
            rag_context = ""
            
            if all_docs:
                # Usamos la utilidad existente para filtrar por relevancia
                rag_context = build_rag_context(trend_topic, all_docs, max_chars=25000)
            
            if not rag_context:
                rag_context = "No se encontró información interna relevante. El análisis se basará en conocimiento general y fuentes externas."

            # B. GENERACIÓN DE DATOS PARA GRÁFICO (JSON OCULTO)
            status.write("📊 Calculando matriz de impacto y madurez...")
            
            # Prompt específico para obtener datos estructurados para el gráfico
            chart_prompt = f"""
            Actúa como estratega de mercado. Basado en el tema '{trend_topic}' y el siguiente contexto, 
            identifica entre 3 y 6 sub-tendencias o hallazgos clave.
            
            Contexto: {rag_context[:10000]}
            
            Tu tarea es calificar cada una para una matriz de priorización.
            Devuelve SOLO un JSON válido con esta estructura (sin markdown):
            [
                {{"Tendencia": "Nombre Corto", "Categoria": "Consumo/Tecnología/Competencia", "Madurez": 8, "Impacto": 9}},
                ...
            ]
            Nota: 'Madurez' (Qué tan consolidada está en el mercado, 1-10) e 'Impacto' (Potencial para el negocio, 1-10).
            """
            
            try:
                # Llamada rápida (NO Streaming) para los datos
                json_resp = call_gemini_api(chart_prompt, generation_config_override={"response_mime_type": "application/json"})
                
                if json_resp:
                    clean_json = clean_gemini_json(json_resp) # Usamos tu nueva función de limpieza
                    chart_data = pd.DataFrame(json.loads(clean_json))
                    st.session_state.mode_state["trend_chart_data"] = chart_data
            except Exception as e:
                print(f"Advertencia: No se pudo generar el gráfico ({e}). Continuando con el texto.")

            # C. GENERACIÓN DEL ANÁLISIS TEXTUAL (STREAMING)
            status.write("✍️ Redactando informe estratégico final...")
            
            final_prompt = get_trend_analysis_prompt(
                topic=trend_topic,
                repo_context=rag_context, # Pasamos el contexto ya filtrado por RAG
                pdf_context="", # Dejamos vacío porque ya unimos PDFs al repo_context arriba
                public_sources_list=selected_public_sources
            )
            
            stream = call_gemini_stream(final_prompt)
            
            if stream:
                status.update(label="¡Análisis completado!", state="complete", expanded=False)
                st.markdown("---")
                
                response_container = st.empty()
                full_response = ""
                
                for chunk in stream:
                    full_response += chunk
                    response_container.markdown(full_response + "▌")
                
                response_container.markdown(full_response)
                
                st.session_state.mode_state["trend_result"] = full_response
                st.session_state.mode_state["trend_topic"] = trend_topic
                
                log_query_event(f"Trend Analysis 2.0: {trend_topic}", mode=c.MODE_TREND_ANALYSIS)
                st.rerun()
            else:
                status.update(label="Error al generar el análisis", state="error")
                st.error("La IA no pudo completar la solicitud. Intenta con un tema más específico.")
