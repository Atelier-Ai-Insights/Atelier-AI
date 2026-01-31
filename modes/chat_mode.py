import streamlit as st
import time
import constants as c

# --- COMPONENTE UNIFICADO ---
from components.chat_interface import render_chat_history, handle_chat_interaction

# Importaciones de Servicios y Utils
try:
    from services.gemini_api import call_gemini_stream
    gemini_available = True
except ImportError:
    gemini_available = False
    def call_gemini_stream(prompt): return None

try:
    from utils import get_relevant_info
except ImportError:
    def get_relevant_info(db, q, f): return "Info simulada"

try:
    from prompts import get_grounded_chat_prompt
    from services.supabase_db import log_query_event
except ImportError:
    def get_grounded_chat_prompt(h, r): return "Prompt simulado"
    def log_query_event(q, mode): pass

# ==========================================
# FUNCIÓN PRINCIPAL DEL CHAT (VISUALMENTE MEJORADA)
# ==========================================
def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.caption("Consulta tus documentos con referencias verificadas.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "chat_history" not in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

    # 2. RENDERIZAR HISTORIAL
    render_chat_history(st.session_state.mode_state["chat_history"], source_mode="chat")

    # 3. INTERACCIÓN DEL USUARIO
    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        # Generador con PASOS VISUALES (Estilo Trend Radar)
        def chat_generator():
            # Iniciamos el contenedor expandido
            with st.status("Iniciando motor de respuesta...", expanded=True) as status:
                
                # Paso 1: Verificación
                if not gemini_available:
                    status.update(label="Error: IA no disponible", state="error")
                    return iter(["⚠️ El servicio de IA no está disponible."])
                
                # Paso 2: Búsqueda (Feedback visual)
                status.write("Escaneando documentos...")
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                if not relevant_info:
                    status.update(label="Sin hallazgos", state="error")
                    return iter(["No encontré información relevante en los documentos seleccionados."])
                
                # Paso 3: Construcción
                status.write("Estructurando evidencia y contexto...")
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-3:]])
                prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                
                # Paso 4: Generación
                status.write("Redactando respuesta con citas...")
                stream = call_gemini_stream(prompt)
                
                if stream:
                    # Al final, cerramos la caja y mostramos check verde
                    status.update(label="¡Respuesta lista!", state="complete", expanded=False)
                    return stream
                else:
                    status.update(label="Error de conexión", state="error")
                    return iter(["Error de conexión con la IA."])

        # Delegamos al componente
        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=chat_generator,
            history_key="chat_history",
            source_mode="chat",
            on_generation_success=lambda resp: log_query_event(user_input, c.MODE_CHAT)
        )

    # 4. BOTÓN LIMPIAR
    if st.session_state.mode_state["chat_history"]:
        st.write("")
        if st.button("Limpiar Conversación", use_container_width=True):
            st.session_state.mode_state["chat_history"] = []
            st.rerun()
