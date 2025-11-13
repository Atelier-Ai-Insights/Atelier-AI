import streamlit as st
from utils import get_relevant_info, reset_report_workflow
from services.gemini_api import call_gemini_api, call_gemini_stream # <-- Ambos
from services.supabase_db import get_monthly_usage, log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_report_prompt1, get_report_prompt2
import constants as c 

def generate_final_report_stream(question, db, selected_files):
    """
    Versión modificada que devuelve un generador para el paso final.
    """
    relevant_info = get_relevant_info(db, question, selected_files)
    
    # Paso 1: Hallazgos (NO Streaming, es interno)
    prompt1 = get_report_prompt1(question, relevant_info)
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    
    # Paso 2: Redacción Final (SÍ Streaming, es lo que ve el usuario)
    prompt2 = get_report_prompt2(question, result1, relevant_info)
    stream2 = call_gemini_stream(prompt2)
    return stream2

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("Herramienta potente para síntesis. Analiza estudios seleccionados y genera informe consolidado.")
    
    if "report" in st.session_state.mode_state and st.session_state.mode_state["report"]:
        st.markdown("---"); st.markdown("### Informe Generado"); 
        st.markdown(st.session_state.mode_state["report"], unsafe_allow_html=True); st.markdown("---")
        
        # Botones de descarga...
        pdf_bytes = generate_pdf_html(st.session_state.mode_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: 
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="Informe.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_rep_btn", use_container_width=True)
    
    else:
        question = st.text_area("Escribe tu consulta...", value=st.session_state.mode_state.get("last_question", ""), height=150)
        
        if st.button("Generar Reporte", use_container_width=True):
            # (Validaciones de límites igual que antes...)
            if not question.strip(): st.warning("Ingresa consulta."); return
            
            st.session_state.mode_state["last_question"] = question
            
            with st.spinner("Analizando documentos y extrayendo hallazgos..."): 
                # Llamamos a nuestra función especial
                stream = generate_final_report_stream(question, db, selected_files)
                
            if stream: 
                st.markdown("---"); st.markdown("### Informe Generado")
                # --- STREAMING ---
                response = st.write_stream(stream)
                
                st.session_state.mode_state["report"] = response
                log_query_event(question, mode=c.MODE_REPORT)
                st.rerun()
            else: 
                st.error("No se pudo generar.")
