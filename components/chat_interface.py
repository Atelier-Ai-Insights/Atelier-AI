import streamlit as st
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial de chat de forma limpia. 
    Los botones de acción ahora se gestionan al final de la conversación.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # Renderizamos el contenido con tooltips, pero sin botones internos
                html_content = process_text_with_tooltips(content)
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Gestiona el envío de mensajes y la respuesta en streaming.
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
            
            # Al terminar el stream, aplicamos tooltips al mensaje final
            final_html = process_text_with_tooltips(full_response)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            
            if on_generation_success:
                on_generation_success(full_response)
                
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
