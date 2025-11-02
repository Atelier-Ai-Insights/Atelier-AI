import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt 

# =====================================================
# MODO: EVALUACIÓN DE PRE-IDEAS
# =====================================================

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Evalúa potencial de idea contra hallazgos.")
    
    if "evaluation_result" in st.session_state:
        st.markdown("---")
        st.markdown("### Evaluación")
        st.markdown(st.session_state.evaluation_result)

        if st.button("Evaluar otra idea", use_container_width=True): 
            del st.session_state["evaluation_result"]
            st.rerun()
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        
        if st.button("Evaluar Idea", use_container_width=True):
            if not idea_input.strip(): 
                st.warning("Describe una idea."); return
                
            with st.spinner("Evaluando potencial..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                prompt = get_idea_eval_prompt(idea_input, context_info)
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.evaluation_result = response
                    # --- Lógica de guardado REVERTIDA ---
                    log_query_event(idea_input, mode="Evaluación de Idea")
                    st.rerun()
                else: 
                    st.error("No se pudo generar evaluación.")