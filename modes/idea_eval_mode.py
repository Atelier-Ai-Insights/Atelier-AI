import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt 
import constants as c
from reporting.pdf_generator import generate_pdf_html
# --- NUEVA IMPORTACIÓN ---
from reporting.docx_generator import generate_docx
from config import banner_file

# =====================================================
# MODO: EVALUACIÓN DE PRE-IDEAS
# =====================================================

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Evalúa potencial de idea contra hallazgos.")
    
    # --- PANTALLA DE RESULTADOS ---
    if "evaluation_result" in st.session_state.mode_state:
        st.markdown("---")
        st.markdown("### Evaluación")
        st.markdown(st.session_state.mode_state["evaluation_result"])

        st.divider() 
        
        # --- BOTONES DE ACCIÓN ---
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["evaluation_result"], 
                title="Evaluación de Idea", 
                banner_path=banner_file
            )
            if pdf_bytes:
                st.download_button("📄 Descargar PDF", data=pdf_bytes, file_name="evaluacion.pdf", mime="application/pdf", width='stretch')

        with col2:
            docx_bytes = generate_docx(
                st.session_state.mode_state["evaluation_result"], 
                title="Evaluación de Idea"
            )
            if docx_bytes:
                st.download_button(
                    "📝 Descargar Word", 
                    data=docx_bytes, 
                    file_name="evaluacion.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    width='stretch',
                    type="primary"
                )

        with col3:
            if st.button("🔄 Evaluar otra", width='stretch'): 
                st.session_state.mode_state.pop("evaluation_result", None)
                st.rerun()

    # --- PANTALLA DE FORMULARIO ---
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        
        if st.button("Evaluar Idea", width='stretch'):
            if not idea_input.strip(): 
                st.warning("Describe una idea."); return
                
            with st.spinner("Conectando con analista virtual..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                prompt = get_idea_eval_prompt(idea_input, context_info)
                
                stream = call_gemini_stream(prompt)
                
                if stream:
                    st.markdown("---")
                    st.markdown("### Evaluación")
                    response = st.write_stream(stream)
                    
                    st.session_state.mode_state["evaluation_result"] = response
                    log_query_event(idea_input, mode=c.MODE_IDEA_EVAL)
                    st.rerun()
                else: 
                    st.error("No se pudo generar evaluación.")
