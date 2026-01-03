import streamlit as st
import time
from services.gemini_api import call_gemini_stream
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from prompts import get_grounded_chat_prompt, get_followup_suggestions_prompt
from services.supabase_db import log_query_event
# --- CORRECCIÓN AQUÍ: Solo importamos SAVE, ya no necesitamos get ni delete ---
from services.memory_service import save_project_insight 
import constants as c
from reporting.pdf_generator import generate_pdf_html
from config import banner_file

def grounded_chat_mode(db, selected_files):
    st.subheader("Chat de Consulta Directa")
    st.caption("Respuestas precisas basadas estrictamente en tu documentación.")

    if not selected_files:
        st.info("👈 Selecciona documentos en el menú lateral para comenzar.")
        return

    # 1. INICIALIZAR HISTORIAL
    if "chat_history" not in st.session_state.mode_state:
        st.session_state.mode_state["chat_history"] = []

    # 2. MOSTRAR HISTORIAL (Con soporte para Tooltips y Pines)
    for idx, msg in enumerate(st.session_state.mode_state["chat_history"]):
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            if msg["role"] == "assistant":
                # Layout: Contenido (90%) | Pin (10%)
                col_txt, col_pin = st.columns([9, 1])
                
                with col_txt:
                    # Procesamos tooltips si existen en el historial
                    content_html = process_text_with_tooltips(msg["content"])
                    st.markdown(content_html, unsafe_allow_html=True)
                
                with col_pin:
                    # Botón Pin discreto
                    with st.popover("📌", use_container_width=False, help="Guardar en Bitácora"):
                        st.markdown("¿Guardar?")
                        if st.button("Sí", key=f"pin_old_{idx}"):
                            if save_project_insight(msg["content"], source_mode="chat"):
                                st.toast("Guardado en bitácora")
                                time.sleep(0.5)
                                st.rerun() # Recargar para que aparezca en el sidebar
            else:
                st.markdown(msg["content"])

    # 3. INPUT DEL USUARIO (Fijo abajo)
    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        # A. Guardar y mostrar pregunta
        st.session_state.mode_state["chat_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            full_response = ""
            placeholder = st.empty()
            
            with render_process_status("Consultando base de conocimientos...", expanded=True) as status:
                # 1. Búsqueda
                relevant_info = get_relevant_info(db, user_input, selected_files)
                if not relevant_info:
                    status.update(label="No encontré información relevante", state="error")
                    st.stop()
                
                # 2. Prompt
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-5:]])
                prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                
                # 3. Stream
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="Generando respuesta...", state="running")
                    for chunk in stream:
                        full_response += chunk
                        placeholder.markdown(full_response + "▌")
                    
                    status.update(label="Respuesta completada", state="complete", expanded=False)
                else:
                    status.update(label="Error de conexión", state="error")
            
            # C. Renderizado Final (Quitar cursor y poner tooltips)
            placeholder.empty()
            
            # Layout respuesta nueva
            col_new_txt, col_new_pin = st.columns([9, 1])
            with col_new_txt:
                final_html = process_text_with_tooltips(full_response)
                st.markdown(final_html, unsafe_allow_html=True)
            
            with col_new_pin:
                with st.popover("📌", use_container_width=False, help="Guardar en Bitácora"):
                    st.markdown("¿Guardar?")
                    if st.button("Sí", key="pin_new_resp"):
                        if save_project_insight(full_response, source_mode="chat"):
                            st.toast("Guardado en bitácora")
                            time.sleep(0.5)
                            st.rerun()

            # Guardar en historial
            st.session_state.mode_state["chat_history"].append({"role": "assistant", "content": full_response})
            
            # Log
            try:
                log_query_event(user_input, mode=c.MODE_CHAT)
            except: pass

    # 4. BOTONES DE ACCIÓN (Exportar Chat)
    if st.session_state.mode_state["chat_history"]:
        st.write("")
        col1, col2 = st.columns(2)
        
        # Generar texto plano para PDF
        chat_text = ""
        for m in st.session_state.mode_state["chat_history"]:
            role = "Usuario" if m["role"] == "user" else "Asistente"
            chat_text += f"**{role}:**\n{m['content']}\n\n"
            
        pdf_bytes = generate_pdf_html(chat_text, title="Historial de Chat", banner_path=banner_file)
        
        with col1:
            if pdf_bytes:
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="Chat_Export.pdf", mime="application/pdf", use_container_width=True)
        
        with col2:
            if st.button("Nueva Conversación", type="secondary", use_container_width=True):
                st.session_state.mode_state["chat_history"] = []
                st.rerun()
