import streamlit as st
import pandas as pd
import altair as alt
import json
import fitz  # PyMuPDF
from utils import get_relevant_info, build_rag_context, clean_gemini_json
from services.gemini_api import call_gemini_stream, call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_trend_analysis_prompt, SOURCE_LENSES
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: ANÁLISIS DE TENDENCIAS 2.0 (RAG + VISUAL PRO)
# =====================================================

def trend_analysis_mode(db_filtered, selected_files):
    st.subheader("Análisis de Tendencias 2.0")
    st.markdown("#### Triangulación Estratégica & Matriz de Impacto")
    
    st.info("Este módulo cruza Data Interna + Evidencia Externa para validar oportunidades de mercado.")

    # --- RESULTADOS ---
    if "trend_result" in st.session_state.mode_state:
        st.divider()
        
        # 1. VISUALIZACIÓN GRÁFICA PRO
        if "trend_chart_data" in st.session_state.mode_state:
            st.markdown("### 📊 Matriz de Oportunidad Estratégica")
            chart_data = st.session_state.mode_state["trend_chart_data"]
            
            # Definir colores semánticos para las etapas
            domain = ["Emergente", "Crecimiento", "Mainstream", "Declive"]
            range_ = ["#FF9F1C", "#2EC4B6", "#E71D36", "#788B9C"] # Naranja, Turquesa, Rojo, Gris

            chart = alt.Chart(chart_data).mark_circle(size=200).encode(
                x=alt.X('Madurez:Q', title='Madurez (1=Nicho, 10=Masivo)', scale=alt.Scale(domain=[0, 11])),
                y=alt.Y('Impacto:Q', title='Impacto en Negocio (1=Bajo, 10=Transformacional)', scale=alt.Scale(domain=[0, 11])),
                
                # COLOR POR ETAPA (Mejora Visual)
                color=alt.Color('Etapa:N', legend=alt.Legend(title="Ciclo de Vida"), scale=alt.Scale(domain=domain, range=range_)),
                
                tooltip=['Tendencia', 'Etapa', 'Madurez', 'Impacto'],
                size=alt.value(600)
            ).properties(
                title=f"Mapa de Calor: {st.session_state.mode_state.get('trend_topic')}",
                height=400
            ).interactive()
            
            # Líneas de cuadrante para referencia
            rules = alt.Chart(pd.DataFrame({'x': [5], 'y': [5]})).mark_rule(color='gray', strokeDash=[3,3]).encode(x='x') + \
                    alt.Chart(pd.DataFrame({'x': [5], 'y': [5]})).mark_rule(color='gray', strokeDash=[3,3]).encode(y='y')

            st.altair_chart(chart + rules, use_container_width=True)

        # 2. REPORTE TEXTUAL
        st.markdown("### 📝 Intelligence Brief")
        st.markdown(st.session_state.mode_state["trend_result"])
        
        # 3. ACCIONES
        col1, col2 = st.columns(2)
        with col1:
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["trend_result"], 
                title=f"Trend Brief - {st.session_state.mode_state.get('trend_topic', 'Análisis')}", 
                banner_path=banner_file
            )
            if pdf_bytes: 
                st.download_button("Descargar Brief PDF", data=pdf_bytes, file_name="trend_brief.pdf", mime="application/pdf", width='stretch', type="primary")
        with col2:
            if st.button("Realizar Nuevo Análisis", width='stretch', type="secondary"):
                keys_to_remove = ["trend_result", "trend_topic", "trend_chart_data"]
                for k in keys_to_remove: st.session_state.mode_state.pop(k, None)
                st.rerun()
        return

    st.divider()

    # --- CONFIGURACIÓN ---
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
            default=[public_options[0], public_options[5]], 
            help="La IA simulará el análisis desde estas perspectivas."
        )

    st.divider()
    trend_topic = st.text_area("Hipótesis o Tendencia a Validar:", height=100, placeholder="Ej: Crecimiento de bebidas vegetales en el segmento premium...")

    if st.button("Ejecutar Triangulación", type="primary", width='stretch'):
        if not trend_topic.strip():
            st.warning("Define un tema primero."); return

        with st.status("🔍 Iniciando motor de tendencias...", expanded=True) as status:
            
            # A. PROCESAMIENTO INTELIGENTE
            status.write("🧠 Minería de datos en documentos (Smart RAG)...")
            
            repo_docs = []
            if use_repo and db_filtered:
                for doc in db_filtered:
                    full_content = ""
                    for grupo in doc.get("grupos", []):
                        full_content += str(grupo.get('contenido_texto', '')) + "\n"
                    if full_content.strip():
                        repo_docs.append({'source': doc.get('nombre_archivo', 'Repo'), 'content': full_content})

            pdf_docs = []
            if uploaded_pdfs:
                for pdf in uploaded_pdfs:
                    try:
                        with fitz.open(stream=pdf.getvalue(), filetype="pdf") as doc:
                            text = "".join([page.get_text() for page in doc])
                            if text.strip():
                                pdf_docs.append({'source': pdf.name, 'content': text})
                    except: pass

            all_docs = repo_docs + pdf_docs
            if all_docs:
                rag_context = build_rag_context(trend_topic, all_docs, max_chars=25000)
            else:
                rag_context = "No se proporcionaron documentos internos."

            # B. GENERACIÓN DE DATOS PARA GRÁFICO (Actualizado con "Etapa")
            status.write("📊 Clasificando ciclo de vida de la tendencia...")
            
            chart_prompt = f"""
            Actúa como estratega de mercado. Basado en el tema '{trend_topic}' y el contexto, 
            identifica entre 3 y 6 sub-tendencias o hallazgos clave.
            
            Contexto: {rag_context[:10000]}
            
            Tu tarea es calificar cada una para una matriz de priorización.
            Devuelve SOLO un JSON válido con esta estructura (sin markdown):
            [
                {{"Tendencia": "Nombre Corto", "Etapa": "Emergente/Crecimiento/Mainstream/Declive", "Madurez": 8, "Impacto": 9}},
                ...
            ]
            Nota: 'Madurez' (1-10), 'Impacto' (1-10). Elige la Etapa que mejor corresponda a la Madurez.
            """
            
            try:
                json_resp = call_gemini_api(chart_prompt, generation_config_override={"response_mime_type": "application/json"})
                if json_resp:
                    clean_json = clean_gemini_json(json_resp)
                    chart_data = pd.DataFrame(json.loads(clean_json))
                    st.session_state.mode_state["trend_chart_data"] = chart_data
            except Exception as e:
                print(f"Error generando gráfico: {e}")

            # C. GENERACIÓN DEL ANÁLISIS TEXTUAL
            status.write("✍️ Redactando Brief Estratégico...")
            
            final_prompt = get_trend_analysis_prompt(
                topic=trend_topic,
                repo_context=rag_context,
                pdf_context="", 
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
                log_query_event(f"Trend 2.0: {trend_topic}", mode=c.MODE_TREND_ANALYSIS)
                st.rerun()
            else:
                status.update(label="Error en la generación", state="error")
                st.error("No se pudo completar el análisis.")
