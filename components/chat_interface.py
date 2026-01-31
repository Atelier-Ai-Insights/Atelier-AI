import streamlit as st
import time
from utils import process_text_with_tooltips
from services.memory_service import save_project_insight

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza una lista de mensajes estandarizada.
    
    Args:
        history (list): Lista de dicts con claves 'role' y 'content'.
        source_mode (str): Etiqueta para saber de qué modo viene el PIN (ej: 'ideation', 'chat').
    """
    if not history:
        return

    for idx, msg in enumerate(history):
        role = msg["role"]
        content = msg["content"]
        
        # Definir Avatar
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # 1. Procesar texto enriquecido (Tooltips)
                # Usamos la función global de utils para mantener la consistencia
                html_content = process_text_with_tooltips(content)
                st.markdown(html_content, unsafe_allow_html=True)
                
                # 2. Botón de PIN (Guardado en Bitácora)
                # Usamos columnas para alinearlo discretamente a la derecha
                col_spacer, col_pin = st.columns([15, 1])
                with col_pin:
                    # Clave única basada en índice y modo para evitar conflictos
                    btn_key = f"pin_{source_mode}_{idx}"
                    
                    if st.button("📌", key=btn_key, help="Guardar en Memoria del Proyecto"):
                        success = save_project_insight(content, source_mode=source_mode)
                        if success:
                            st.toast("✅ Guardado en bitácora")
                        else:
                            st.toast("❌ Error al guardar")
            else:
                # Mensaje del usuario (Texto plano o Markdown simple)
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Maneja la lógica común de:
    1. Mostrar input usuario.
    2. Llamar a la IA (Streaming).
    3. Guardar en historial.
    """
    # Agregar pregunta del usuario al historial
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    
    # Mostrar inmediatamente el mensaje del usuario
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Generar respuesta del asistente
    with st.chat_message("assistant", avatar="✨"):
        full_response = ""
        placeholder = st.empty()
        
        # Ejecutamos el generador (stream)
        stream = response_generator_func()
        
        if stream:
            for chunk in stream:
                full_response += chunk
                placeholder.markdown(full_response + "▌")
            
            # Renderizado final limpio con Tooltips
            final_html = process_text_with_tooltips(full_response)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            # Guardar en historial
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            
            # Botón PIN para la respuesta recién generada
            col_s, col_p = st.columns([15, 1])
            with col_p:
                if st.button("📌", key=f"pin_new_{source_mode}_{int(time.time())}", help="Guardar"):
                    save_project_insight(full_response, source_mode=source_mode)
                    st.toast("✅ Guardado")
            
            # Callback opcional (ej: para logs)
            if on_generation_success:
                on_generation_success(full_response)
                
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
