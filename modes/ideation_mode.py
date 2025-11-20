import streamlit as st
from utils import get_relevant_info, reset_chat_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file
from prompts import get_ideation_prompt
import constants as c 

# =====================================================
# MODO: CONVERSACIONES CREATIVAS (IDEACIÓN)
# =====================================================

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Explora ideas novedosas basadas en hallazgos.")
    
    # --- ¡MODIFICADO! ---
    if "chat_history" not in st.session_state.mode_state: 
        st.session_state.mode_state["chat_history"] = []
        
    # --- ¡MODIFICADO! ---
    for msg in st.session_state.mode_state["chat_history"]:
        with st.chat_message(msg['role'], avatar="✨" if msg['role'] == "Asistente" else "👤"): 
            st.markdown(msg['message'])
            
    user_input = st.chat_input("Lanza una idea o pregunta...")
    
    if user_input:
        # --- ¡MODIFICADO! ---
        st.session_state.mode_state["chat_history"].append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario", avatar="👤"): 
            st.markdown(user_input)
            
        with st.chat_message("Asistente", avatar="✨"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Generando ideas...")
            
            relevant = get_relevant_info(db, user_input, selected_files)
            # --- ¡MODIFICADO! ---
            conv_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.mode_state["chat_history"][-10:])
            
            conv_prompt = get_ideation_prompt(conv_history, relevant)
            
            resp = call_gemini_api(conv_prompt)
            
            if resp: 
                message_placeholder.markdown(resp)
                log_query_event(user_input, mode=c.MODE_IDEATION) 
                # --- ¡MODIFICADO! ---
                st.session_state.mode_state["chat_history"].append({
                    "role": "Asistente", 
                    "message": resp
                })
                st.rerun()
            else: 
                message_placeholder.error("Error generando respuesta.")
                
    # --- ¡MODIFICADO! ---
    if st.session_state.mode_state["chat_history"]:
        col1, col2 = st.columns([1,1])
        with col1:
            # --- ¡MODIFICADO! ---
            chat_content_raw = "\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.mode_state["chat_history"])
            chat_content_for_pdf = chat_content_raw.replace("](#)", "]")
            pdf_bytes = generate_pdf_html(chat_content_for_pdf, title="Historial Creativo", banner_path=banner_file)
            
            if pdf_bytes: 
                st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf", width='stretch')
        with col2: 
            st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn", width='stretch')
