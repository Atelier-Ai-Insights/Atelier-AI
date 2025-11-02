import streamlit as st
from utils import get_relevant_info, reset_chat_workflow
from services.gemini_api import call_gemini_api
# --- ¡IMPORTACIÓN ACTUALIZADA! ---
from services.supabase_db import log_query_event, log_query_feedback
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_ideation_prompt

# =====================================================
# MODO: CONVERSACIONES CREATIVAS (IDEACIÓN)
# =====================================================

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Explora ideas novedosas basadas en hallazgos.")
    
    if "chat_history" not in st.session_state: 
        st.session_state.chat_history = []
        
    # --- CAMBIO 1: El Callback AHORA ACEPTA el query_id ---
    def ideation_feedback_callback(feedback, query_id):
        # Usar .get() para seguridad y score=0 para 'thumbs_down'
        score = 1 if feedback.get('score') == 'thumbs_up' else 0
        
        log_query_feedback(query_id, score)
        st.toast("¡Gracias por tu feedback!")
        
    # --- BUCLE DE VISUALIZACIÓN DE CHAT (MODIFICADO) ---
    for msg in st.session_state.chat_history:
        if msg['role'] == "Asistente":
            with st.chat_message("Asistente", avatar="✨"):
                st.markdown(msg['message'])
                
                # --- ¡CAMBIOS 2 y 3! ---
                if msg.get('query_id'):
                    # 2. Usamos el nombre oficial st.feedback
                    st.feedback( 
                        key=f"feedback_{msg['query_id']}", # 3. Key única
                        on_submit=ideation_feedback_callback,
                        args=(msg.get('query_id'),) # 4. Pasar el query_id como argumento
                    )
                # --- FIN DE LOS CAMBIOS ---
        else: # Mensajes del usuario
            with st.chat_message("Usuario", avatar="👤"):
                st.markdown(msg['message'])
            
    user_input = st.chat_input("Lanza una idea o pregunta...")
    
    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario", avatar="👤"): 
            st.markdown(user_input)
            
        with st.chat_message("Asistente", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Generando ideas...")
            
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])
            
            conv_prompt = get_ideation_prompt(conv_history, relevant)
            
            resp = call_gemini_api(conv_prompt)
            
            if resp: 
                message_placeholder.markdown(resp)
                
                # (Esta parte ya estaba correcta)
                # 1. Logueamos la consulta y obtenemos el ID
                query_id = log_query_event(user_input, mode="Conversaciones creativas")
                
                # 2. Guardamos el ID junto con el mensaje del asistente
                st.session_state.chat_history.append({
                    "role": "Asistente", 
                    "message": resp,
                    "query_id": query_id # El ID se usa como 'key' para el feedback
                })
                
            else: 
                message_placeholder.error("Error generando respuesta.")
                
    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
            # (La lógica de PDF se mantiene igual, ya estaba corregida)
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history)
            chat_content_for_pdf = chat_content_raw.replace("](#)", "]")
            pdf_bytes = generate_pdf_html(chat_content_for_pdf, title="Historial Creativo", banner_path=banner_file)
            
            if pdf_bytes: 
                st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn", use_container_width=True)