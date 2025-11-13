import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream # <-- Usar Stream
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
import constants as c 

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")
    
    if "generated_concept" in st.session_state.mode_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.mode_state["generated_concept"])

        if st.button("Generar nuevo concepto", use_container_width=True): 
            st.session_state.mode_state.pop("generated_concept")
            st.rerun()
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        
        if st.button("Generar Concepto", use_container_width=True):
            if not product_idea.strip(): 
                st.warning("Describe tu idea."); return
                
            with st.spinner("Iniciando generación creativa..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = get_concept_gen_prompt(product_idea, context_info)
                
                # --- STREAMING ---
                stream = call_gemini_stream(prompt)
                
                if stream:
                    st.markdown("---")
                    st.markdown("### Concepto Generado")
                    response = st.write_stream(stream)
                    
                    st.session_state.mode_state["generated_concept"] = response
                    log_query_event(product_idea, mode=c.MODE_CONCEPT)
                else: 
                    st.error("No se pudo generar concepto.")
