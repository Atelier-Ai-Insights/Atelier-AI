import streamlit as st
import time
from services.gemini_api import call_gemini_api, call_gemini_stream
from utils import get_relevant_info, render_process_status, process_text_with_tooltips # <--- IMPORTANTE
from prompts import get_report_prompt1, get_report_prompt2
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from services.supabase_db import log_query_event
import constants as c

def report_mode(db, selected_files):
    st.subheader("📝 Generador de Informes de Investigación")
    
    # 1. Input
    user_question = st.text_input("¿Qué objetivo de investigación deseas abordar?", placeholder="Ej: Analizar la percepción de precios en la categoría...")
    
    if not selected_files:
        st.warning("Selecciona documentos en el menú lateral.")
        return

    # 2. Botón de Acción
    if st.button("Generar Informe", type="primary"):
        if not user_question: return
        
        # Resetear estado anterior
        for k in ["report_step1", "report_final"]: st.session_state.mode_state.pop(k, None)
        
        with render_process_status("Iniciando investigación...", expanded=True) as status:
            
            # --- FASE 1: BÚSQUEDA Y HALLAZGOS ---
            status.write("🔍 Fase 1: Escaneando documentos y extrayendo evidencia...")
            relevant_info = get_relevant_info(db, user_question, selected_files, top_k=15)
            
            if not relevant_info:
                status.update(label="No se encontró información relevante.", state="error")
                return

            prompt1 = get_report_prompt1(user_question, relevant_info)
            findings = call_gemini_api(prompt1)
            st.session_state.mode_state["report_step1"] = findings
            
            # --- FASE 2: REDACCIÓN ---
            status.write("✍️ Fase 2: Redactando informe ejecutivo...")
            prompt2 = get_report_prompt2(user_question, findings, relevant_info)
            
            final_report_stream = call_gemini_stream(prompt2)
            
            # Consumir el stream para guardarlo en variable
            full_response = ""
            placeholder = st.empty()
            
            # En modo streaming no podemos procesar tooltips en tiempo real fácilmente sin romper el HTML
            # Así que mostramos el stream raw, y al final renderizamos el bonito.
            for chunk in final_report_stream:
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            
            st.session_state.mode_state["report_final"] = full_response
            placeholder.empty() # Limpiamos el stream sucio
            
            status.update(label="¡Informe completado!", state="complete", expanded=False)
            
            # Log
            log_query_event(f"Reporte: {user_question}", mode=c.MODE_REPORT)

    # 3. Visualización de Resultados (SIEMPRE PERSISTENTE)
    if "report_final" in st.session_state.mode_state:
        final_text = st.session_state.mode_state["report_final"]
        
        # RENDERIZADO CON TOOLTIPS
        # Procesamos el texto final para convertir las citas en tooltips interactivos
        html_content = process_text_with_tooltips(final_text)
        
        st.divider()
        st.markdown(html_content, unsafe_allow_html=True)
        
        # Botón PDF
        st.write("")
        pdf_bytes = generate_pdf_html(final_text, title="Informe de Investigación", banner_path=banner_file)
        if pdf_bytes:
            st.download_button(
                label="📥 Descargar Informe PDF",
                data=pdf_bytes,
                file_name="Informe_Investigacion.pdf",
                mime="application/pdf",
                type="secondary"
            )
