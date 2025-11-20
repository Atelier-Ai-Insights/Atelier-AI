import streamlit as st
from utils import get_relevant_info
from services.gemini_api import call_gemini_stream 
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
import constants as c 
# --- ¡NUEVAS IMPORTACIONES! ---
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

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
        
        st.divider() # Línea separadora visual

        # --- BOTONES DE ACCIÓN ---
        col1, col2 = st.columns(2)
        
        with col1:
            # Generar PDF
            pdf_bytes = generate_pdf_html(
                st.session_state.mode_state["generated_concept"], 
                title="Concepto de Innovación", 
                banner_path=banner_file
            )
            
            if pdf_bytes:
                st.download_button(
                    label="Descargar Concepto PDF", 
                    data=pdf_bytes, 
                    file_name="concepto_generado.pdf", 
                    mime="application/pdf", 
                    width='stretch'
                )
            else:
                st.error("No se pudo generar el PDF.")

        with col2:
            if st.button("Generar nuevo concepto", width='stretch'): 
                # Limpiar estado
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
                
                # --- STREAMING ---
                stream = call_gemini_stream(prompt)
                
                if stream:
                    st.markdown("---")
                    st.markdown("### Concepto Generado")
                    # Efecto de escritura
                    response = st.write_stream(stream)
                    
                    # Guardar en estado
                    st.session_state.mode_state["generated_concept"] = response
                    log_query_event(product_idea, mode=c.MODE_CONCEPT)
                    
                    # Rerun para mostrar los botones inmediatamente
                    st.rerun()
                else: 
                    st.error("No se pudo generar concepto.")
