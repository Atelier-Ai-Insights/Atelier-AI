import streamlit as st
import time
import constants as c
from components.chat_interface import render_chat_history, handle_chat_interaction
from components.export_utils import render_final_actions

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
    st.subheader("Chat de Consulta Directa")
    st.caption("Consulta tus documentos con referencias verificadas.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    if "chat_history" not in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

    render_chat_history(st.session_state.mode_state["chat_history"], source_mode="chat")

    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        def chat_generator():
            status_box = st.empty()
            
            with status_box.status("Iniciando motor de respuesta...", expanded=True) as status:
                if not gemini_available:
                    status.update(label="Error: IA no disponible", state="error")
                    return iter(["⚠️ El servicio de IA no está disponible."])
                
                status.write("Escaneando documentos (Motor RAG)...")
                relevant_info = get_relevant_info(db, user_input, selected_files)
                
                if not relevant_info:
                    status.update(label="Sin hallazgos", state="error")
                    return iter(["No encontré información relevante en los documentos seleccionados."])
                
                status.write("Estructurando evidencia y contexto...")
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-3:]])
                prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                
                status.write("Redactando respuesta con citas...")
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="¡Respuesta lista!", state="complete", expanded=False)
                else:
                    status.update(label="Error de conexión", state="error")
                    return iter(["Error de conexión con la IA."])

            if stream:
                time.sleep(0.7) 
                status_box.empty() 
                return stream

        handle_chat_interaction(
            prompt=user_input,
            response_generator_func=chat_generator,
            history_key="chat_history",
            source_mode="chat",
            on_generation_success=lambda resp: log_query_event(user_input, c.MODE_CHAT)
        )

    if st.session_state.mode_state["chat_history"]:
        full_content = ""
        for msg in st.session_state.mode_state["chat_history"]:
            role_label = "Usuario" if msg["role"] == "user" else "Atelier AI"
            full_content += f"### {role_label}\n{msg['content']}\n\n"
        
        def reset_chat_workflow():
            st.session_state.mode_state["chat_history"] = []

        render_final_actions(
            content=full_content,
            title="Chat_Consulta_Atelier",
            mode_key="chat_directo",
            on_reset_func=reset_chat_workflow
        )
