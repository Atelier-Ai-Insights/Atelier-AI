import streamlit as st
import re
import time
from utils import process_text_with_tooltips
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight

# --- VENTANA EMERGENTE DE REFERENCIAS ---
@st.dialog("Referencias y Evidencia")
def show_sources_dialog(content):
    """
    Muestra la evidencia técnica en un modal.
    """
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.info("No hay referencias detalladas para esta respuesta.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Simplificación de nombre
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"**[{cid}] {clean_name}**")
            st.caption("Evidencia detectada:")
            st.info(quote.strip().strip('"'))

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial con la barra de acciones inferior: Feedback + Ver Referencias + Pin.
    """
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # Limpieza visual del contenido técnico
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)[0]
                display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
                
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # --- BARRA DE ACCIONES INFERIOR (Solo para la IA) ---
                # Columna 1-2: Pulgares | Columna 3: Botón Texto | Columna 4: Pin
                col_up, col_down, col_ref, col_pin, col_spacer = st.columns([0.8, 0.8, 2.5, 0.8, 6])
                key_base = f"{source_mode}_{idx}"

                with col_up:
                    if st.button("👍", key=f"up_{key_base}"):
                        log_message_feedback(content, source_mode, "up")
                        st.toast("Feedback registrado")

                with col_down:
                    if st.button("👎", key=f"down_{key_base}"):
                        log_message_feedback(content, source_mode, "down")
                        st.toast("Feedback registrado")

                with col_ref:
                    if "|||" in content:
                        if st.button("Ver Referencias", key=f"ref_{key_base}", use_container_width=True):
                            show_sources_dialog(content)

                with col_pin:
                    if st.button("📌", key=f"pin_{key_base}"):
                        if save_project_insight(content, source_mode=source_mode):
                            st.toast("✅ Guardado")
                            time.sleep(0.5)
                            st.rerun()
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Maneja la interacción y fuerza recarga para mostrar la barra de acciones.
    """
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    
    # Renderizado inmediato del usuario
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Respuesta de la IA
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
            
            st.rerun() # Esto garantiza que aparezca la barra de iconos al terminar
            return full_response
