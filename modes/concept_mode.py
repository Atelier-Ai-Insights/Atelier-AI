import streamlit as st
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_concept_gen_prompt
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
import constants as c

def concept_generation_mode(db, selected_files):
    st.subheader("Generador de Conceptos")
    st.caption("Estructura ideas de innovación en conceptos de marketing sólidos (Insight + Beneficio + RTB).")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "concept_history" not in st.session_state.mode_state:
        st.session_state.mode_state["concept_history"] = []

    # 2. MOSTRAR HISTORIAL
    for msg in st.session_state.mode_state["concept_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                st.markdown(process_text_with_tooltips(msg["content"]), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # 3. INPUT FIJO ABAJO (ESTANDARIZADO)
    concept_input = st.chat_input("Describe la idea base para el concepto...")

    if concept_input:
        # A. Mensaje Usuario
        st.session_state.mode_state["concept_history"].append({"role": "user", "content": concept_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(concept_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            with render_process_status("Diseñando concepto ganador...", expanded=True) as status:
                status.write("Buscando evidencia de soporte...")
                relevant_info = get_relevant_info(db, concept_input, selected_files)
                
                status.write("Estructurando Insight, Beneficio y RTB...")
                prompt = get_concept_gen_prompt(concept_input, relevant_info)
                response = call_gemini_api(prompt)
                
                if response:
                    status.update(label="Concepto Generado", state="complete", expanded=False)
                    
                    st.session_state.mode_state["concept_history"].append({"role": "assistant", "content": response})
                    enriched_html = process_text_with_tooltips(response)
                    st.markdown(enriched_html, unsafe_allow_html=True)
                    
                    log_query_event(f"Concepto: {concept_input[:30]}", mode=c.MODE_CONCEPT)
                else:
                    status.update(label="Error al generar", state="error")

    # 4. BOTONES DE ACCIÓN
    if st.session_state.mode_state["concept_history"]:
        st.divider()
        
        full_text = ""
        for m in st.session_state.mode_state["concept_history"]:
            role = "Idea Base" if m["role"] == "user" else "Concepto Desarrollado"
            full_text += f"**{role}:**\n{m['content']}\n\n---\n\n"

        pdf_bytes = generate_pdf_html(full_text, title="Conceptos de Producto", banner_path=banner_file)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if pdf_bytes:
                st.download_button("PDF", data=pdf_bytes, file_name="Conceptos_Generados.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            if st.button("Limpiar", use_container_width=True):
                st.session_state.mode_state["concept_history"] = []
                st.rerun()
