import streamlit as st
import constants as c
from components.chat_interface import render_chat_history, handle_chat_interaction

try:
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(prompt): return None

try:
    from utils import get_relevant_info
except ImportError:
    def get_relevant_info(db, q, f): return ""

try:
    from services.supabase_db import log_query_event
    from prompts import get_ideation_prompt
except ImportError:
    def log_query_event(q, m): pass
    def get_ideation_prompt(h, r): return ""

try:
    from reporting.pdf_generator import generate_pdf_html
    from config import banner_file
except ImportError:
    generate_pdf_html = None
    banner_file = None

# ==========================================
# FUNCIÓN PRINCIPAL: IDEACIÓN (VISUALMENTE MEJORADA)
# ==========================================
def ideacion_mode(db, selected_files):
    st.subheader("Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. HISTORIAL
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # 2. RENDERIZADO
    render_chat_history(st.session_state.mode_state["ideation_history"], source_mode="ideation")

    # 3. INPUT
    if user_input := st.chat_input("Escribe un desafío creativo..."):
        
        # Generador con PASOS VISUALES
        def ideation_generator():
            with st.status("Activando motor creativo...", expanded=True) as status:
                
                status.write("Conectando con la base de conocimiento...")
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["Error: Servicio de IA no disponible."])

                # Paso 1: RAG
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                # Paso 2: Historial
                status.write("Analizando contexto de la sesión...")
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                
                # Paso 3: Prompt
                status.write("Aplicando Pensamiento Lateral...")
                prompt = get_ideation_prompt(hist_str, relevant_info)
                
                # Paso 4: Stream
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                    return stream
                else:
                    status.update(label="Error al generar", state="error")
                    return iter(["Error al conectar con el motor creativo."])

        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=ideation_generator,
            history_key="ideation_history",
            source_mode="ideation",
            on_generation_success=lambda resp: log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
        )

    # 4. BOTONES
    if st.session_state.mode_state["ideation_history"]:
        st.write("") 
        col1, col2 = st.columns(2)
        with col1:
            if generate_pdf_html:
                full_chat_text = ""
                for m in st.session_state.mode_state["ideation_history"]:
                    role_title = "Usuario" if m["role"] == "user" else "Atelier AI"
                    full_chat_text += f"**{role_title}:**\n{m['content']}\n\n"
                try:
                    pdf_bytes = generate_pdf_html(full_chat_text, title="Sesión de Ideación", banner_path=banner_file)
                    if pdf_bytes:
                        st.download_button("Descargar PDF", data=pdf_bytes, file_name="Ideacion.pdf", mime="application/pdf", type="secondary", use_container_width=True)
                except: pass
        with col2:
            if st.button("Nueva Búsqueda", type="secondary", use_container_width=True):
                st.session_state.mode_state["ideation_history"] = []
                st.rerun()
