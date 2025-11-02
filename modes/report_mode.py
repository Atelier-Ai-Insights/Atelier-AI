import streamlit as st
from utils import get_relevant_info, reset_report_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import get_monthly_usage, log_query_event, log_query_feedback
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_report_prompt1, get_report_prompt2

# =====================================================
# MODO: GENERAR REPORTE DE REPORTES
# =====================================================

# --- CAMBIO 1: El Callback AHORA ACEPTA el query_id ---
def report_feedback_callback(feedback, query_id):
    if query_id:
        # Usar .get() para seguridad y score=0 para 'thumbs_down'
        score = 1 if feedback.get('score') == 'thumbs_up' else 0
        log_query_feedback(query_id, score)
        st.toast("¡Gracias por tu feedback!")
        # Para ocultar los botones después de votar
        st.session_state.voted_on_last_report = True
    else:
        st.toast("Error: No se encontró el ID de la consulta.")

def generate_final_report(question, db, selected_files):
    # (Esta función no cambia)
    relevant_info = get_relevant_info(db, question, selected_files)
    prompt1 = get_report_prompt1(question, relevant_info)
    result1 = call_gemini_api(prompt1)
    if result1 is None: return None
    prompt2 = get_report_prompt2(question, result1, relevant_info)
    result2 = call_gemini_api(prompt2)
    if result2 is None: return None
    return result2

def report_mode(db, selected_files):
    st.markdown("### Generar Reporte de Reportes")
    st.markdown("Herramienta potente para síntesis. Analiza estudios seleccionados y genera informe consolidado.")
    
    if "report" in st.session_state and st.session_state["report"]:
        st.markdown("---"); st.markdown("### Informe Generado"); st.markdown(st.session_state["report"], unsafe_allow_html=True); st.markdown("---")
    
    question = st.text_area("Escribe tu consulta para el reporte…", value=st.session_state.get("last_question", ""), height=150, key="report_question")
    
    if st.button("Generar Reporte", use_container_width=True):
        report_limit = st.session_state.plan_features.get('reports_per_month', 0); current_reports = get_monthly_usage(st.session_state.user, "Generar un reporte de reportes")
        if current_reports >= report_limit and report_limit != float('inf'): st.error(f"Límite de {int(report_limit)} reportes alcanzado."); return
        if not question.strip(): st.warning("Ingresa una consulta."); return
        
        st.session_state["last_question"] = question
        with st.spinner("Generando informe..."): 
            report = generate_final_report(question, db, selected_files)
            
        if report is None: 
            st.error("No se pudo generar."); st.session_state.pop("report", None)
        else: 
            st.session_state["report"] = report
            query_id = log_query_event(question, mode="Generar un reporte de reportes")
            st.session_state["last_report_query_id"] = query_id
            st.session_state["voted_on_last_report"] = False
            
            # --- ¡CAMBIO 2: st.rerun() ELIMINADO! ---
            # st.rerun() # <-- Esta línea se borra
            
    if "report" in st.session_state and st.session_state["report"]:
        
        # --- ¡SECCIÓN DE FEEDBACK CORREGIDA! ---
        query_id = st.session_state.get("last_report_query_id")
        if query_id and not st.session_state.get("voted_on_last_report", False):
            # CAMBIO 3: Usar st.feedback (nombre oficial)
            st.feedback(
                key=f"feedback_{query_id}", # CAMBIO 4: Key única
                on_submit=report_feedback_callback,
                args=(query_id,) # CAMBIO 5: Pasar el query_id como argumento
            )
        # --- FIN DE LA SECCIÓN DE FEEDBACK ---

        # (Botones de descarga y nueva consulta)
        pdf_bytes = generate_pdf_html(st.session_state["report"], title="Informe Final", banner_path=banner_file)
        col1, col2 = st.columns(2)
        with col1:
            if pdf_bytes: 
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="Informe_AtelierIA.pdf", mime="application/pdf", use_container_width=True)
            else: 
                st.button("Error PDF", disabled=True, use_container_width=True)
        with col2: 
            st.button("Nueva consulta", on_click=reset_report_workflow, key="new_report_query_btn", use_container_width=True)