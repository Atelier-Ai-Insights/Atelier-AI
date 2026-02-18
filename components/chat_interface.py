import streamlit as st
import re
import html
import time
from utils import process_text_with_tooltips
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight

# --- VENTANA EMERGENTE DE FUENTES ---
@st.dialog("Fuentes y Evidencia")
def show_sources_dialog(content):
    """
    Extrae la metadata oculta [1] Archivo ||| Cita y la muestra en un modal.
    """
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.info("No hay citas detalladas registradas para esta respuesta.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Simplificación de nombre (quitando fechas y extensiones)
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"**[{cid}] {clean_name}**")
            st.caption("Evidencia detectada en el documento:")
            st.info(quote.strip().strip('"'))

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial con la nueva barra de iconos: Feedback + Fuentes + Pin.
    """
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # 1. Limpieza visual: ocultamos bloques técnicos para la app
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)[0]
                display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
                
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # --- BARRA DE ICONOS ---
                c_up, c_down, c_src, c_pin, c_spacer = st.columns([1, 1, 1, 1, 8])
                key_base = f"{source_mode}_{idx}"

                with c_up:
                    if st.button("👍", key=f"up_{key_base}", help="Respuesta útil"):
                        if log_message_feedback(content, source_mode, "up"):
                            st.toast("Feedback registrado 👍")

                with c_down:
                    if st.button("👎", key=f"down_{key_base}", help="Respuesta inexacta"):
                        if log_message_feedback(content, source_mode, "down"):
                            st.toast("Gracias por tu feedback 🤔")

                with c_src:
                    if "|||" in content:
                        if st.button("📖", key=f"src_{key_base}", help="Ver Fuentes y Citas"):
                            show_sources_dialog(content)

                with c_pin:
                    if st.button("📌", key=f"pin_{key_base}", help="Guardar en Bitácora"):
                        if save_project_insight(content, source_mode=source_mode):
                            st.toast("✅ Guardado")
                            time.sleep(0.5)
                            st.rerun()
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Maneja la entrada del usuario y la respuesta de IA con recarga para iconos.
    """
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        full_response = ""
        placeholder = st.empty()
        stream = response_generator_func()
        
        if stream:
            for chunk in stream:
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            
            st.rerun() 
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
