import streamlit as st
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from prompts import get_idea_eval_prompt
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
import constants as c

def idea_evaluator_mode(db, selected_files):
    st.subheader("Evaluador de Ideas")
    st.caption("Somete tu idea al juicio crítico de los datos de mercado.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "eval_history" not in st.session_state.mode_state:
        st.session_state.mode_state["eval_history"] = []

    # 2. MOSTRAR HISTORIAL (Conversación hacia arriba)
    for msg in st.session_state.mode_state["eval_history"]:
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                st.markdown(process_text_with_tooltips(msg["content"]), unsafe_allow_html=True)
            else:
                st.markdown(msg["content"])

    # 3. INPUT FIJO ABAJO (ESTANDARIZADO)
    idea_input = st.chat_input("Escribe la idea que quieres evaluar...")

    if idea_input:
        # A. Mostrar mensaje usuario
        st.session_state.mode_state["eval_history"].append({"role": "user", "content": idea_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(idea_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            with render_process_status("Analizando viabilidad...", expanded=True) as status:
                relevant = get_relevant_info(db, idea_input, selected_files)
                prompt = get_idea_eval_prompt(idea_input, relevant)
                response = call_gemini_api(prompt)
                
                if response:
                    status.update(label="Evaluación Completada", state="complete", expanded=False)
                    
                    # Guardar y Mostrar
                    st.session_state.mode_state["eval_history"].append({"role": "assistant", "content": response})
                    enriched_html = process_text_with_tooltips(response)
                    st.markdown(enriched_html, unsafe_allow_html=True)
                    
                    log_query_event(f"Evaluación: {idea_input[:30]}", mode=c.MODE_IDEA_EVAL)
                else:
                    status.update(label="Error en el análisis", state="error")

    # 4. BOTÓN DESCARGA PDF (De la última evaluación o todo el historial)
    if st.session_state.mode_state["eval_history"]:
        st.divider()
        
        # Generar PDF de toda la sesión
        full_text = ""
        for m in st.session_state.mode_state["eval_history"]:
            role = "Idea" if m["role"] == "user" else "Evaluación"
            full_text += f"**{role}:**\n{m['content']}\n\n---\n\n"

        pdf_bytes = generate_pdf_html(full_text, title="Sesión de Evaluación de Ideas", banner_path=banner_file)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if pdf_bytes:
                st.download_button("PDF", data=pdf_bytes, file_name="Evaluacion_Ideas.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            if st.button("Limpiar", use_container_width=True):
                st.session_state.mode_state["eval_history"] = []
                st.rerun()
