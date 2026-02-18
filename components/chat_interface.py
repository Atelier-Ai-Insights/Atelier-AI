import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial de chat omitiendo visualmente el bloque de fuentes 
    para mantener una interfaz limpia, pero conservando los tooltips.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"]
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # Dividimos el texto para ocultar la sección de fuentes en la UI de la app
                # Buscamos variaciones de "Fuentes Verificadas", "Fuentes Consultadas", etc.
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', content, flags=re.IGNORECASE)[0]
                
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Gestiona la interacción del chat y aplica la misma lógica de limpieza visual
    al finalizar la generación por streaming.
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
            
            # Aplicamos limpieza visual al mensaje final generado
            display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes( Verificadas| Consultadas)?\s*:?', full_response, flags=re.IGNORECASE)[0]
            
            final_html = process_text_with_tooltips(display_text)
            placeholder.markdown(final_html, unsafe_allow_html=True)
            
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            
            if on_generation_success:
                on_generation_success(full_response)
                
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
