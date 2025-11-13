import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream # <-- Usar Stream
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt 
import constants as c 

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluación de Pre-Ideas")
    st.markdown("Evalúa potencial de idea contra hallazgos.")
    
    if "evaluation_result" in st.session_state.mode_state:
        st.markdown("---")
        st.markdown("### Evaluación")
        st.markdown(st.session_state.mode_state["evaluation_result"])

        if st.button("Evaluar otra idea", use_container_width=True): 
            del st.session_state.mode_state["evaluation_result"]
            st.rerun()
    else:
        idea_input = st.text_area("Describe la idea a evaluar:", height=150, placeholder="Ej: Yogures con probióticos...")
        
        if st.button("Evaluar Idea", use_container_width=True):
            if not idea_input.strip(): 
                st.warning("Describe una idea."); return
                
            # El spinner se muestra solo mientras conecta, luego arranca el stream
            with st.spinner("Conectando con analista virtual..."):
                context_info = get_relevant_info(db, idea_input, selected_files)
                prompt = get_idea_eval_prompt(idea_input, context_info)
                
                # --- STREAMING ---
                stream = call_gemini_stream(prompt)
                
                if stream:
                    st.markdown("---")
                    st.markdown("### Evaluación")
                    response = st.write_stream(stream)
                    
                    st.session_state.mode_state["evaluation_result"] = response
                    log_query_event(idea_input, mode=c.MODE_IDEA_EVAL)
                    # No hacemos rerun aquí para mantener el texto en pantalla recién generado
                else: 
                    st.error("No se pudo generar evaluación.")
