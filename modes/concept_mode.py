import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
import constants as c 
from config import banner_file

# --- GENERADORES (Top Level Import - FASE 1) ---
from reporting.pdf_generator import generate_pdf_html
from reporting.docx_generator import generate_docx

# =====================================================
# MODO: GENERACIÓN DE CONCEPTOS
# =====================================================

def concept_generation_mode(db, selected_files):
    
    st.subheader("Generación de Conceptos")
    st.markdown("Genera concepto de producto/servicio a partir de idea y hallazgos.")
    
    # --- PANTALLA DE RESULTADOS ---
    if "generated_concept" in st.session_state.mode_state:
        st.markdown("---")
        st.markdown("### Concepto Generado")
        st.markdown(st.session_state.mode_state["generated_concept"])
        
        st.divider()

        col1, col2, col3 = st.columns(3)
        
        with col1:
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["generated_concept"], 
                title="Concepto de Innovación", 
                banner_path=banner_file
            )
            if pdf_bytes:
                st.download_button("📄 Descargar PDF", data=pdf_bytes, file_name="concepto.pdf", mime="application/pdf", width='stretch')

        with col2:
            docx_bytes = generate_docx(
                st.session_state.mode_state["generated_concept"], 
                title="Concepto de Innovación"
            )
            if docx_bytes:
                st.download_button(
                    "📝 Descargar Word", 
                    data=docx_bytes, 
                    file_name="concepto.docx", 
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    width='stretch',
                    type="primary"
                )

        with col3:
            if st.button("🔄 Nuevo Concepto", width='stretch'): 
                st.session_state.mode_state.pop("generated_concept")
                st.rerun()

    # --- PANTALLA DE FORMULARIO ---
    else:
        product_idea = st.text_area("Describe tu idea:", height=150, placeholder="Ej: Snack saludable...")
        
        if st.button("Generar Concepto", width='stretch'):
            if not product_idea.strip(): 
                st.warning("Describe tu idea."); return
                
            with st.spinner("Iniciando generación creativa..."):
                context_info = get_relevant_info(db, product_idea, selected_files)
                prompt = get_concept_gen_prompt(product_idea, context_info)
                
                stream = call_gemini_stream(prompt)
                
                if stream:
                    st.markdown("---")
                    st.markdown("### Concepto Generado")
                    response = st.write_stream(stream)
                    
                    st.session_state.mode_state["generated_concept"] = response
                    log_query_event(product_idea, mode=c.MODE_CONCEPT)
                    st.rerun()
                else: 
                    st.error("No se pudo generar concepto.")
