import streamlit as st
from utils import get_relevant_info, reset_chat_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import get_daily_usage, log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_grounded_chat_prompt # <-- ¡ARREGLO AÑADIDO AQUÍ!

# =====================================================
# MODO: CHAT DE CONSULTA DIRECTA (GROUNDED)
# =====================================================

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.markdown("Preguntas específicas, respuestas basadas solo en hallazgos seleccionados.")
    
    if "chat_history" not in st.session_state: 
        st.session_state.chat_history = []
        
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']): 
            st.markdown(msg['message'])
            
    user_input = st.chat_input("Escribe tu pregunta...")
    
    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"): 
            st.markdown(user_input)
            
        query_limit = st.session_state.plan_features.get('chat_queries_per_day', 0)
        current_queries = get_daily_usage(st.session_state.user, "Chat de Consulta Directa")
        
        if current_queries >= query_limit and query_limit != float('inf'): 
            st.error(f"Límite de {int(query_limit)} consultas diarias alcanzado.")
            return
            
        with st.chat_message("Asistente"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Pensando...")
            
            relevant_info = get_relevant_info(db, user_input, selected_files)
            conversation_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])
            
            # --- CÓDIGO ACTUALIZADO ---
            # Ahora llama a la función desde prompts.py
            grounded_prompt = get_grounded_chat_prompt(conversation_history, relevant_info)
            # --- FIN DEL CAMBIO ---
          
            response = call_gemini_api(grounded_prompt)
            
            if response: 
                message_placeholder.markdown(response)
                st.session_state.chat_history.append({"role": "Asistente", "message": response})
                log_query_event(user_input, mode="Chat de Consulta Directa")
            else: 
                message_placeholder.error("Error al generar respuesta.")
                
    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
            pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial Consulta", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_consulta.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            st.button("Nueva Conversación", on_click=reset_chat_workflow, key="new_grounded_chat_btn", use_container_width=True)