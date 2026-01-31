import streamlit as st
import constants as c

# --- NUEVO: IMPORTAMOS EL COMPONENTE UNIFICADO ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# 1. Servicios IA
try:
    # Cambiamos a STREAM para mejorar la velocidad percibida
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
    from prompts import get_ideation_prompt
except ImportError:
    def log_query_event(q, m): pass
    def get_ideation_prompt(h, r): return ""

# 4. PDF Config
try:
    from reporting.pdf_generator import generate_pdf_html
    from config import banner_file
except ImportError:
    generate_pdf_html = None
    banner_file = None


# ==========================================
# FUNCIÓN PRINCIPAL: IDEACIÓN (OPTIMIZADA)
# ==========================================
def ideacion_mode(db, selected_files):
    st.subheader("Ideación Estratégica")
    st.caption("Brainstorming creativo fundamentado en datos del repositorio.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "ideation_history" not in st.session_state.mode_state:
        st.session_state.mode_state["ideation_history"] = []

    # 2. RENDERIZAR HISTORIAL (Automático)
    render_chat_history(st.session_state.mode_state["ideation_history"], source_mode="ideation")

    # 3. INTERACCIÓN DEL USUARIO
    if user_input := st.chat_input("Escribe un desafío creativo..."):
        
        # Definimos el generador específico para Ideación
        def ideation_generator():
            with st.status("Conectando puntos...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["Error: Servicio de IA no disponible."])

                # Recuperar contexto RAG
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                # Historial para contexto
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["ideation_history"][-3:]])
                
                # Prompt específico de Ideación (Lateral Thinking)
                prompt = get_ideation_prompt(hist_str, relevant_info)
                
                # Llamada streaming (Mejora UX respecto a la versión anterior)
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Ideas generadas!", state="complete", expanded=False)
                    return stream
                else:
                    status.update(label="Error al generar", state="error")
                    return iter(["Error al conectar con el motor creativo."])

        # Delegamos al componente visual
        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=ideation_generator,
            history_key="ideation_history",
            source_mode="ideation",
            on_generation_success=lambda resp: log_query_event(f"Ideación: {user_input[:50]}", mode=c.MODE_IDEATION)
        )

    # 4. BOTONES DE ACCIÓN (PDF / Limpiar)
    # Mantenemos esta lógica aquí porque es específica de este modo
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
                        st.download_button(
                            label="Descargar PDF",
                            data=pdf_bytes,
                            file_name="Ideacion_Creativa.pdf",
                            mime="application/pdf",
                            type="secondary",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"Error PDF: {e}")

        with col2:
            if st.button("Nueva Búsqueda", type="secondary", use_container_width=True):
                st.session_state.mode_state["ideation_history"] = []
                st.rerun()
