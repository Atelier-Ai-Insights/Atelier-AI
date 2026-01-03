import streamlit as st
from utils import get_relevant_info, render_process_status, process_text_with_tooltips # <--- IMPORTANTE
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
import constants as c

def concept_generation_mode(db, selected_files):
    st.subheader("Generador de Conceptos de Producto")
    st.caption("Estructura ideas de innovación en conceptos de marketing sólidos.")

    idea_input = st.text_area("Describe tu idea o hipótesis de producto:", height=100)
    
    if st.button("Desarrollar Concepto", type="primary", disabled=not selected_files):
        if not idea_input:
            st.warning("Escribe una idea base.")
            return

        with render_process_status("Validando con el mercado...", expanded=True) as status:
            status.write("Buscando evidencia de soporte...")
            relevant_info = get_relevant_info(db, idea_input, selected_files)
            
            status.write("Estructurando concepto...")
            prompt = get_concept_gen_prompt(idea_input, relevant_info)
            response = call_gemini_api(prompt)
            
            st.session_state.mode_state["last_concept"] = response
            status.update(label="Concepto Generado", state="complete", expanded=False)
            
            log_query_event(f"Concepto: {idea_input[:50]}...", mode=c.MODE_CONCEPT)

    if "last_concept" in st.session_state.mode_state:
        # Renderizar con Tooltips
        content = st.session_state.mode_state["last_concept"]
        enriched_html = process_text_with_tooltips(content)
        
        st.divider()
        st.markdown(enriched_html, unsafe_allow_html=True)
        
        pdf_bytes = generate_pdf_html(content, title="Concepto de Producto", banner_path=banner_file)
        if pdf_bytes:
            st.download_button("Descargar Concepto", data=pdf_bytes, file_name="Concepto.pdf", mime="application/pdf")
