import streamlit as st
import time
import constants as c

# --- IMPORTACIONES SEGURAS ---
try:
    from services.gemini_api import call_gemini_stream
    from utils import get_relevant_info, render_process_status, process_text_with_tooltips
    from prompts import get_grounded_chat_prompt
    from services.supabase_db import log_query_event
    from services.memory_service import save_project_insight 
    from config import banner_file
except ImportError as e:
    st.error(f"Error importando módulos del chat: {e}")
    st.stop()

# Importación condicional para PDF (para que no rompa si falla reportlab)
try:
    from reporting.pdf_generator import generate_pdf_html
except ImportError:
    generate_pdf_html = None # Deshabilitamos PDF si falla la librería

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
        role_avatar = "✨" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=role_avatar):
            # A. Mostrar contenido procesado (Tooltips)
            if msg["role"] == "assistant":
                content_html = process_text_with_tooltips(msg["content"])
                st.markdown(content_html, unsafe_allow_html=True)
                
                # B. BOTÓN PIN MINIMALISTA (Protegido)
                col_spacer, col_pin = st.columns([15, 1])
                with col_pin:
                    if st.button("📌", key=f"pin_hist_{idx}", help="Guardar en Bitácora"):
                        try:
                            if save_project_insight(msg["content"], source_mode="chat"):
                                st.toast("✅ Guardado")
                                time.sleep(1) 
                                st.rerun()    
                        except Exception as e:
                            st.error(f"No se pudo guardar: {e}")
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
            
            # Usamos un contenedor seguro para el proceso de IA
            try:
                with render_process_status("Consultando base de conocimientos...", expanded=True) as status:
                    relevant_info = get_relevant_info(db, user_input, selected_files)
                    
                    if not relevant_info:
                        status.update(label="Sin información relevante en los documentos seleccionados.", state="error")
                        full_response = "No encontré información relevante en los documentos seleccionados para responder tu pregunta."
                        placeholder.markdown(full_response)
                    else:
                        hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"][-5:]])
                        prompt = get_grounded_chat_prompt(hist_str, relevant_info)
                        
                        stream = call_gemini_stream(prompt)
                        
                        if stream:
                            status.update(label="Generando respuesta...", state="running")
                            for chunk in stream:
                                full_response += chunk
                                placeholder.markdown(full_response + "▌")
                            status.update(label="Listo", state="complete", expanded=False)
                        else:
                            status.update(label="Error de conexión con IA", state="error")
                            full_response = "Lo siento, hubo un problema de conexión con el servicio de IA."
            
            except Exception as e:
                full_response = f"Ocurrió un error inesperado: {str(e)}"
                placeholder.error(full_response)
            
            # C. Render Final + PIN NUEVO
            placeholder.empty()
            final_html = process_text_with_tooltips(full_response)
            st.markdown(final_html, unsafe_allow_html=True)
            
            # Botón Pin Minimalista para la respuesta nueva
            col_spacer_new, col_pin_new = st.columns([15, 1])
            with col_pin_new:
                if st.button("📌", key="pin_new_resp", help="Guardar en Bitácora"):
                    try:
                        if save_project_insight(full_response, source_mode="chat"):
                            st.toast("✅ Guardado")
                            time.sleep(1)
                            st.rerun()
                    except: pass

            st.session_state.mode_state["chat_history"].append({"role": "assistant", "content": full_response})
            try: log_query_event(user_input, mode=c.MODE_CHAT)
            except: pass

    # 4. BOTONES EXPORTAR
    if st.session_state.mode_state["chat_history"]:
        st.write("")
        col1, col2 = st.columns(2)
        
        # Generación de PDF Protegida
        pdf_bytes = None
        if generate_pdf_html: # Solo si la librería cargó bien
            try:
                chat_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.mode_state["chat_history"]])
                pdf_bytes = generate_pdf_html(chat_text, title="Historial Chat", banner_path=banner_file)
            except Exception as e:
                # Si falla el PDF, solo mostramos aviso en consola, no rompemos la UI
                print(f"Error generando PDF: {e}")

        with col1:
            if pdf_bytes:
                st.download_button("Descargar PDF", data=pdf_bytes, file_name="chat_historial.pdf", mime="application/pdf", use_container_width=True)
            elif generate_pdf_html is None:
                st.warning("Exportar PDF no disponible (faltan librerías)")
        
        with col2:
            if st.button("Limpiar Chat", use_container_width=True):
                st.session_state.mode_state["chat_history"] = []
                st.rerun()
