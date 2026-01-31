import streamlit as st
import constants as c

# --- NUEVO: COMPONENTE UNIFICADO ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# 1. Servicios IA
try:
    # Cambiamos a STREAM para mejor UX
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(prompt): return None

# 2. Utilidades
try:
    from utils import get_relevant_info
except ImportError:
    def get_relevant_info(db, q, f): return ""

# 3. Base de Datos y Memoria
try:
    from services.supabase_db import log_query_event
    from prompts import get_concept_gen_prompt 
except ImportError:
    def log_query_event(q, m): pass
    def get_concept_gen_prompt(h, r): return ""

# 4. PDF Config
try:
    from reporting.pdf_generator import generate_pdf_html
    from config import banner_file
except ImportError:
    generate_pdf_html = None
    banner_file = None


# ==========================================
# FUNCIÓN PRINCIPAL: CONCEPTOS (OPTIMIZADA)
# ==========================================
def concept_generation_mode(db, selected_files):
    st.subheader("Generador de Conceptos")
    st.caption("Estructura ideas de innovación en conceptos de marketing sólidos (Insight + Beneficio + RTB).")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "concept_history" not in st.session_state.mode_state:
        st.session_state.mode_state["concept_history"] = []

    # 2. RENDERIZAR HISTORIAL (Automático)
    render_chat_history(st.session_state.mode_state["concept_history"], source_mode="concept")

    # 3. INTERACCIÓN DEL USUARIO
    if concept_input := st.chat_input("Describe la idea base para el concepto..."):

        # Definimos el generador
        def concept_generator():
            with st.status("Diseñando concepto ganador...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["Error: IA no disponible."])

                # Búsqueda RAG
                status.write("Buscando evidencia de soporte...")
                relevant_info = get_relevant_info(db, concept_input, selected_files)
                
                # Prompt de Concepto
                status.write("Estructurando Insight, Beneficio y RTB...")
                prompt = get_concept_gen_prompt(concept_input, relevant_info)
                
                # Llamada Streaming
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="Concepto Generado", state="complete", expanded=False)
                    return stream
                else:
                    status.update(label="Error al generar", state="error")
                    return iter(["Error al generar el concepto."])

        # Delegamos al componente visual
        handle_chat_interaction(
            prompt=concept_input,
            response_generator_func=concept_generator,
            history_key="concept_history",
            source_mode="concept",
            on_generation_success=lambda resp: log_query_event(f"Concepto: {concept_input[:30]}", mode=c.MODE_CONCEPT)
        )

    # 4. BOTONES DE ACCIÓN (PDF / Nueva Sesión)
    if st.session_state.mode_state["concept_history"]:
        st.write("") 
        
        col1, col2 = st.columns(2)
        
        with col1:
            if generate_pdf_html:
                full_text = ""
                for m in st.session_state.mode_state["concept_history"]:
                    role = "Idea Base" if m["role"] == "user" else "Concepto Desarrollado"
                    full_text += f"**{role}:**\n{m['content']}\n\n---\n\n"

                try:
                    pdf_bytes = generate_pdf_html(full_text, title="Conceptos de Producto", banner_path=banner_file)
                    if pdf_bytes:
                        st.download_button(
                            label="Descargar PDF", 
                            data=pdf_bytes, 
                            file_name="Conceptos_Generados.pdf", 
                            mime="application/pdf", 
                            type="secondary",
                            use_container_width=True
                        )
                except Exception: pass
        
        with col2:
            if st.button("Nueva Sesión", type="secondary", use_container_width=True):
                st.session_state.mode_state["concept_history"] = []
                st.rerun()
