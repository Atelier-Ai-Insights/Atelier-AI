import streamlit as st
from utils import get_relevant_info, reset_report_workflow
from services.gemini_api import call_gemini_api, call_gemini_stream
from services.supabase_db import get_monthly_usage, log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_report_prompt1, get_report_prompt2
import constants as c 

def generate_final_report_stream(question, db, selected_files, status_container=None):
    """
    Versión modificada que acepta un contenedor de estado para actualizar el progreso visual.
    """
    # Paso 1: Búsqueda y Hallazgos
    relevant_info = get_relevant_info(db, question, selected_files)
    
    if status_container:
        status_container.write("🧠 Identificando hallazgos clave en la base de conocimientos...")
        
    prompt1 = get_report_prompt1(question, relevant_info)
    result1 = call_gemini_api(prompt1)
    
    if result1 is None: return None
    
    # Paso 2: Redacción Final
    if status_container:
        status_container.write("✍️ Redactando informe ejecutivo final...")
        
    prompt2 = get_report_prompt2(question, result1, relevant_info)
    stream2 = call_gemini_stream(prompt2)
    return stream2

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("Herramienta potente para síntesis. Analiza estudios seleccionados y genera informe consolidado.")
    
    # --- PANTALLA DE RESULTADOS ---
    if "report" in st.session_state.mode_state and st.session_state.mode_state["report"]:
        st.markdown("---"); st.markdown("### Informe Generado"); 
        st.markdown(st.session_state.mode_state["report"], unsafe_allow_html=True); st.markdown("---")
        
        pdf_bytes = generate_pdf_html(st.session_state.mode_state["report"], title="Informe Final", banner_path=banner_file)
        
        # --- MEJORA UX: Botones organizados ---
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: 
                st.download_button("📄 Descargar PDF", data=pdf_bytes, file_name="Informe_Atelier.pdf", mime="application/pdf", width='stretch', type="primary")
        with col2: 
            st.button("🔄 Nueva consulta", on_click=reset_report_workflow, key="new_rep_btn", width='stretch')
    
    # --- PANTALLA DE CONSULTA ---
    else:
        question = st.text_area("Escribe tu consulta...", value=st.session_state.mode_state.get("last_question", ""), height=150, placeholder="Ej: ¿Cuáles son los principales insights sobre la categoría de lácteos en 2024?")
        
        if st.button("Generar Reporte", width='stretch', type="primary"):
            if not question.strip(): st.warning("Por favor, ingresa una consulta."); return
            
            st.session_state.mode_state["last_question"] = question
            
            # --- MEJORA UX: st.status paso a paso ---
            stream = None
            with st.status("🚀 Iniciando motor de investigación...", expanded=True) as status:
                status.write("📂 Accediendo al repositorio de documentos...")
                
                # Llamamos a la función pasando el 'status' para que actualice los mensajes
                stream = generate_final_report_stream(question, db, selected_files, status_container=status)
                
                if stream:
                    status.update(label="¡Análisis completado! Generando respuesta...", state="complete", expanded=False)
                else:
                    status.update(label="Hubo un problema al generar el reporte.", state="error")

            if stream: 
                st.markdown("---")
                st.markdown("### Informe Generado")
                response = st.write_stream(stream)
                
                st.session_state.mode_state["report"] = response
                log_query_event(question, mode=c.MODE_REPORT)
                st.rerun()
            else: 
                st.error("No se pudo generar el reporte. Intenta reformular tu pregunta.")
