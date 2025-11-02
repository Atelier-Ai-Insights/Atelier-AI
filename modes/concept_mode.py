import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
import constants as c # <--- IMPORTACIÓN AÑADIDA

# =====================================================
# MODO: GENERACIÓN DE CONCEPTOS
# =====================================================

def concept_generation_mode(db, selected_files):
    st.subheader("Generación de Conceptos")
    st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")
    
    if "generated_concept" in st.session_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.generated_concept)

        if st.button("Generar nuevo concepto", use_container_width=True): 
            st.session_state.pop("generated_concept")
            st.rerun()
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        
        if st.button("Generar Concepto", use_container_width=True):
            if not product_idea.strip(): 
                st.warning("Describe tu idea."); return
                
            with st.spinner("Generando concepto..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = get_concept_gen_prompt(product_idea, context_info)
                response = call_gemini_api(prompt)
                
                if response: 
                    st.session_state.generated_concept = response
                    # --- Lógica de guardado REVERTIDA ---
                    log_query_event(product_idea, mode=c.MODE_CONCEPT) # <-- MODIFICADO
                    st.rerun()
                else: 
                    st.error("No se pudo generar concepto.")