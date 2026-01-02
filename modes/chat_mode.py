import streamlit as st
from utils import get_relevant_info, reset_chat_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_grounded_chat_prompt
import constants as c 

# =====================================================
# MODO: CHAT DE CONSULTA DIRECTA (GROUNDED)
# =====================================================

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown("Respuestas a preguntas específicas basadas solo en hallazgos de estudios seleccionados.")
    
    # --- ¡MODIFICADO! ---
    if "chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["chat_history"] = []
        
    # --- ¡MODIFICADO! ---
    for msg in st.session_state.mode_state["chat_history"]:
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            
    user_input = st.chat_input("Escribe tu pregunta...")
    
    if user_input:
        # --- ¡MODIFICADO! ---
        st.session_state.mode_state["chat_history"].append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario", avatar="👤"): 
            st.markdown(user_input)
            
        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0)
        current_queries = get_daily_usage(st.session_state.user, c.MODE_CHAT)
        
        if current_queries >= query_limit and query_limit != float('inf'): 
            st.error(f"Límite de {int(query_limit)} consultas diarias alcanzado."); return
            
        with st.chat_message("Asistente", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Pensando...")
            
            relevant_info = get_relevant_info(db, user_input, selected_files)
            # --- ¡MODIFICADO! ---
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info)
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                log_query_event(user_input, mode=c.MODE_CHAT)
                # --- ¡MODIFICADO! ---
                st.session_state.mode_state["chat_history"].append({
                    "role": "Asistente", 
                    "message": response
                })
                st.rerun()
            else: 
                message_placeholder.error("Error al generar respuesta.")
                
    # --- ¡MODIFICADO! ---
    if st.session_state.mode_state["chat_history"]:
        col1, col2 = st.columns([1,1])
        with col1:
            # --- ¡MODIFICADO! ---
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.mode_state["chat_history"])
            chat_content_for_pdf = chat_content_raw.replace("](#)", "]")
            pdf_bytes = generate_pdf_html(chat_content_for_pdf, title="Historial Consulta", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", width='stretch')
        with col2: 
            # Esta función ya fue actualizada en utils.py
            st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn", width='stretch')
