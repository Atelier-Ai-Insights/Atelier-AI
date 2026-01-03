import streamlit as st
import time
from services.gemini_api import call_gemini_stream
from utils import get_relevant_info, render_process_status, process_text_with_tooltips
from prompts import get_grounded_chat_prompt
from services.supabase_db import log_query_event
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

    # 2. MOSTRAR HISTORIAL
    for idx, msg in enumerate(st.session_state.mode_state["chat_history"]):
        with st.chat_message(msg["role"], avatar="✨" if msg["role"]=="assistant" else "👤"):
            # A. Mostrar contenido procesado (Tooltips)
            if msg["role"] == "assistant":
                content_html = process_text_with_tooltips(msg["content"])
                st.markdown(content_html, unsafe_allow_html=True)
                
                # B. BOTÓN PIN MINIMALISTA (Abajo a la derecha)
                # Usamos columnas para empujarlo a la derecha sin romper el texto
                col_spacer, col_pin = st.columns([15, 1])
                with col_pin:
                    if st.button("📌", key=f"pin_hist_{idx}", help="Guardar en Bitácora", type="secondary"):
                        if save_project_insight(msg["content"], source_mode="chat"):
                            st.toast("✅ Guardado")
                            time.sleep(1) # Dar tiempo a la BD
                            st.rerun()    # Recargar para ver en Sidebar
            else:
                st.markdown(msg["content"])

    # 3. INPUT DEL USUARIO
    if user_input := st.chat_input("Haz una pregunta sobre tus documentos..."):
        
        # A. Guardar pregunta
        st.session_state.mode_state["chat_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        # B. Generar Respuesta
        with st.chat_message("assistant", avatar="✨"):
            full_response = ""
            placeholder = st.empty()
            
            with render_process_status("Consultando base de conocimientos...", expanded=True) as status:
                relevant_info = get_relevant_info(db, user_input, selected_files)
                if not relevant_info:
                    status.update(label="Sin información relevante", state="error"); st.stop()
                
                hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-5:]])
                prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                stream = call_gemini_stream(prompt)
                
                if stream:
                    status.update(label="Generando...", state="running")
                    for chunk in stream:
                        full_response += chunk
                        placeholder.markdown(full_response + "▌")
                    status.update(label="Listo", state="complete", expanded=False)
                else:
                    status.update(label="Error", state="error")
            
            # C. Render Final + PIN NUEVO
            placeholder.empty()
            final_html = process_text_with_tooltips(full_response)
            st.markdown(final_html, unsafe_allow_html=True)
            
            # Botón Pin Minimalista para la respuesta nueva
            col_spacer_new, col_pin_new = st.columns([15, 1])
            with col_pin_new:
                if st.button("📌", key="pin_new_resp", help="Guardar en Bitácora"):
                    if save_project_insight(full_response, source_mode="chat"):
                        st.toast("✅ Guardado")
                        time.sleep(1)
                        st.rerun()

            st.session_state.mode_state["chat_history"].append({"role": "assistant", "content": full_response})
            try: log_query_event(user_input, mode=c.MODE_CHAT)
            except: pass

    # 4. BOTONES EXPORTAR
    if st.session_state.mode_state["chat_history"]:
        st.write("")
        col1, col2 = st.columns(2)
        # Lógica de PDF igual que antes...
        chat_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"]])
        pdf_bytes = generate_pdf_html(chat_text, title="Historial Chat", banner_path=banner_file)
        
        with col1:
            if pdf_bytes: st.download_button("PDF", data=pdf_bytes, file_name="chat.pdf", mime="application/pdf", use_container_width=True)
        with col2:
            if st.button("Limpiar", use_container_width=True):
                st.session_state.mode_state["chat_history"] = []
                st.rerun()
