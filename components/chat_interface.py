import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial de forma ultra-limpia en la UI, 
    manteniendo los metadatos técnicos intactos en el estado de la sesión.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"] # Contenido original con metadatos técnicos
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # LIMPIEZA SOLO PARA LA PANTALLA:
                # 1. Cortar visualmente si detecta el bloque técnico |||
                display_text = re.split(r'\[\d+\].*?\|\|\|', content, flags=re.DOTALL)[0]
                # 2. Cortar si detecta la palabra "Fuentes" escrita al final por la IA
                display_text = re.split(r'\n\s*(\*\*|##)?\s*Fuentes', display_text, flags=re.IGNORECASE)[0]
                
                html_content = process_text_with_tooltips(display_text.strip())
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """Maneja la entrada del usuario y guarda la respuesta íntegra para el modal."""
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
            
            # GUARDADO CRÍTICO: Se guarda con metadatos técnicos intactos
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            
            st.rerun() 
            return full_response
        else:
            st.error("Error: No se recibió respuesta de la IA.")
            return None
