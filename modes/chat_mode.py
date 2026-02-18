import streamlit as st
import time
import constants as c
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions

# --- CARGA DE SERVICIOS CON MANEJO DE ERRORES ---
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

def grounded_chat_mode(db, selected_files):
    """Función principal del modo de chat directo."""
    st.subheader("Chat de Consulta Directa")
    st.caption("Consulta tus documentos con referencias verificadas.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # Inicializar el estado del historial
    if "chat_history" not in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

    # 1. Renderizar historial (limpio visualmente)
    render_chat_history(st.session_state.mode_state["chat_history"], source_mode="chat")

    # 2. Entrada del usuario
    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        def chat_generator():
            status_box = st.empty()
            with status_box.status("Iniciando motor de respuesta...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="IA no disponible", state="error")
                    return iter(["⚠️ El servicio de IA no está disponible."])
                
                status.write("Escaneando documentos...")
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                if not relevant_info:
                    status.update(label="Sin hallazgos", state="error")
                    return iter(["No encontré información relevante."])
                
                status.write("Construyendo respuesta...")
                # Contexto de los últimos 3 mensajes
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-3:]])
                prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Listo!", state="complete", expanded=False)
                    time.sleep(0.5)
                    status_box.empty()
                    return stream
                else:
                    status.update(label="Error de IA", state="error")
                    return iter(["Error de conexión con la IA."])

        # Procesar interacción y guardar respuesta completa
        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=chat_generator,
            history_key="chat_history",
            source_mode="chat",
            on_generation_success=lambda resp: log_query_event(user_input, c.MODE_CHAT)
        )

    # 3. Acciones de exportación y modal de referencias
    if st.session_state.mode_state["chat_history"]:
        full_content = ""
        for msg in st.session_state.mode_state["chat_history"]:
            role_label = "Usuario" if msg["role"] == "user" else "Atelier AI"
            full_content += f"### {role_label}\n{msg['content']}\n\n"
        
        def reset_chat_workflow():
            st.session_state.mode_state["chat_history"] = []

        render_final_actions(
            content=full_content,
            title="Consulta_Atelier",
            mode_key="chat_directo",
            on_reset_func=reset_chat_workflow
        )
