import streamlit as st
import re
import time
import html
from utils import process_text_with_tooltips
from services.supabase_db import log_message_feedback
from services.memory_service import save_project_insight

# --- 1. VENTANA EMERGENTE (MODAL) ---
# Esta función crea la ventana emergente igual a la de búsquedas guardadas
@st.dialog("Referencias y Evidencia Documental")
def show_sources_dialog(content):
    """
    Extrae la información técnica y la muestra en un modal.
    """
    # Buscamos el patrón: [1] NombreArchivo ||| Cita: "..."
    pattern = r'\[(\d+)\]\s*([^\[\]\|\n]+?)\s*\|\|\|\s*(.+?)(?=\n\[\d+\]|$|\n\n)'
    matches = re.findall(pattern, content, flags=re.DOTALL)
    
    if not matches:
        st.warning("No se encontraron detalles técnicos de las citas para este mensaje.")
        return

    for cid, fname, quote in matches:
        with st.container(border=True):
            # Simplificación del nombre del archivo (quita fechas y extensiones)
            clean_name = re.sub(r'\.(pdf|docx|xlsx|txt)$', '', fname, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d{2,4}[-_]\d{1,2}[-_]\d{1,2}[-_]', '', clean_name).replace("In-ATL_", "")
            
            st.markdown(f"### Fuente [{cid}]: {clean_name}")
            st.markdown("**Cita textual:**")
            st.info(f"\"{quote.strip()}\"")

# --- 2. RENDERIZADO DEL HISTORIAL ---
def render_chat_history(history, source_mode="chat"):
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # Guardamos la marca de si hay referencias antes de limpiar el texto
                has_ref = "|||" in content
                
                # Limpieza visual para la App (oculta el bloque técnico)
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)[0]
                display_text = re.split(r'\[\d+\].*?\|\|\|', display_text, flags=re.DOTALL)[0]
                
                # Renderizar texto principal con tooltips
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # --- BARRA DE ACCIONES (Feedback, Referencias, Pin) ---
                # Ajustamos anchos: pulgares pequeños, botón de referencias ancho
                col1, col2, col3, col4, col5 = st.columns([0.5, 0.5, 2.0, 0.5, 5])
                k = f"{source_mode}_{idx}"

                with col1:
                    if st.button("👍", key=f"up_{k}"):
                        log_message_feedback(content, source_mode, "up")
                        st.toast("¡Gracias!")

                with col2:
                    if st.button("👎", key=f"down_{k}"):
                        log_message_feedback(content, source_mode, "down")
                        st.toast("Registrado")

                with col3:
                    # EL BOTÓN SOLICITADO
                    if has_ref:
                        if st.button("🔍 Ver Referencias", key=f"btn_ref_{k}", use_container_width=True):
                            show_sources_dialog(content)

                with col4:
                    if st.button("📌", key=f"pin_{k}"):
                        if save_project_insight(content, source_mode=source_mode):
                            st.toast("📌 Guardado")
                            time.sleep(0.5)
                            st.rerun()
            else:
                st.markdown(content)

# --- 3. GESTIÓN DE INTERACCIÓN ---
def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
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
            
            # Al terminar, guardamos la respuesta completa (con metadata)
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            
            if on_generation_success:
                on_generation_success(full_response)
            
            # RECARGA VITAL: Para que Streamlit reconozca los botones de la barra de acciones
            st.rerun()
            return full_response
        else:
            st.error("No se pudo obtener respuesta de la IA.")
            return None
