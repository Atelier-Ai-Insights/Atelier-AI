import streamlit as st
import time
from utils import process_text_with_tooltips
# Importamos las funciones de guardado
from services.memory_service import save_project_insight
from services.supabase_db import log_message_feedback

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial con una barra de acciones integrada (Feedback + PIN).
    """
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # 1. Mostrar el texto enriquecido con tooltips
                html_content = process_text_with_tooltips(content)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # --- BARRA DE ACCIONES INTEGRADA ---
                # Usamos columnas estrechas para agrupar los botones tipo icono
                # Estructura: [👍] [👎] [Espacio.....] [📌]
                col_up, col_down, col_spacer, col_pin = st.columns([1, 1, 10, 1])
                
                # Clave base única para este mensaje
                key_base = f"{source_mode}_{idx}"

                # Botón Like 👍
                with col_up:
                    if st.button("👍", key=f"up_{key_base}", help="Respuesta útil"):
                        if log_message_feedback(content, source_mode, "up"):
                            st.toast("Gracias por el feedback! 👍")

                # Botón Dislike 👎
                with col_down:
                    if st.button("👎", key=f"down_{key_base}", help="Respuesta inexacta o irrelevante"):
                        if log_message_feedback(content, source_mode, "down"):
                            st.toast("Gracias. Revisaremos esto. 🤔")

                # Botón PIN 📌 (Integrado estéticamente)
                with col_pin:
                    if st.button("📌", key=f"pin_{key_base}", help="Guardar en Memoria del Proyecto"):
                        success = save_project_insight(content, source_mode=source_mode)
                        if success:
                            st.toast("✅ Guardado en bitácora")
                        else:
                            st.toast("❌ Error al guardar")

            else:
                # Mensaje del usuario (simple)
                st.markdown(content)

# Nota: handle_chat_interaction no necesita cambios para el botón PIN de la nueva respuesta,
# ya que la próxima vez que se renderice el historial completo, aparecerá la barra integrada.
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
            
            final_html = process_text_with_tooltips(full_response)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            
            if on_generation_success:
                on_generation_success(full_response)
                
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
