import streamlit as st
from utils import get_relevant_info, reset_chat_workflow
from services.gemini_api import call_gemini_api
from services.supabase_db import log_query_event
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

# =====================================================
# MODO: CONVERSACIONES CREATIVAS (IDEACIÓN)
# =====================================================

def ideacion_mode(db, selected_files):
    st.subheader("Conversaciones Creativas")
    st.markdown("Explora ideas novedosas basadas en hallazgos.")
    
    if "chat_history" not in st.session_state: 
        st.session_state.chat_history = []
        
    for msg in st.session_state.chat_history:
        with st.chat_message(msg['role']): 
            st.markdown(msg['message'])
            
    user_input = st.chat_input("Lanza una idea o pregunta...")
    
    if user_input:
        st.session_state.chat_history.append({"role": "Usuario", "message": user_input})
        with st.chat_message("Usuario"): 
            st.markdown(user_input)
            
        with st.chat_message("Asistente"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Generando ideas...")
            
            relevant = get_relevant_info(db, user_input, selected_files)
            conv_history = "\n".join(f"{m['role']}: {m['message']}" for m in st.session_state.chat_history[-10:])
            
            conv_prompt = (
                f"**Tarea:** Experto Mkt/Innovación creativo. Conversación inspiradora con usuario sobre ideas/soluciones basadas **solo** en 'Información de contexto' e 'Historial'.\n\n"
                f"**Historial:**\n{conv_history}\n\n"
                f"**Contexto (hallazgos):**\n{relevant}\n\n"
                f"**Instrucciones:**\n"
                f"1. Rol: Experto creativo.\n"
                f"2. Base: Solo 'Contexto' (resultados/hallazgos).\n"
                f"3. Objetivo: Ayudar a explorar soluciones creativas conectando datos.\n"
                f"4. Inicio (1er msg asistente): Breve resumen estudios relevantes.\n"
                f"5. Estilo: Claro, sintético, inspirador.\n"
                f"6. Citas: IEEE [1] (ej: estudio snacks [1]).\n\n"
                f"**Respuesta creativa:**"
            )
            
            resp = call_gemini_api(conv_prompt)
            
            if resp: 
                message_placeholder.markdown(resp)
                st.session_state.chat_history.append({"role": "Asistente", "message": resp})
                log_query_event(user_input, mode="Conversaciones creativas")
            else: 
                message_placeholder.error("Error generando respuesta.")
                
    if st.session_state.chat_history:
        col1, col2 = st.columns([1,1])
        with col1:
            pdf_bytes = generate_pdf_html("\n\n".join(f"**{m['role']}:** {m['message']}" for m in st.session_state.chat_history), title="Historial Creativo", banner_path=banner_file)
            if pdf_bytes: 
                st.download_button("Descargar Chat PDF", data=pdf_bytes, file_name="chat_creativo.pdf", mime="application/pdf", use_container_width=True)
        with col2: 
            st.button("Nueva conversación", on_click=reset_chat_workflow, key="new_chat_btn", use_container_width=True)
