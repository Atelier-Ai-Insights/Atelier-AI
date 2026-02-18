import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial de forma limpia en la UI.
    Mantiene los metadatos intactos en la variable 'content' para el modal.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"] # Contenido original preservado
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # LIMPIEZA VISUAL:
                # Ocultamos todo lo que esté después del separador técnico |||
                display_text = re.split(r'\|\|\|', content)[0]
                
                # También ocultamos si la IA escribió una lista de "Fuentes:" al final
                display_text = re.split(r'\n\s*Fuentes:', display_text, flags=re.IGNORECASE)[0]
                
                html_content = process_text_with_tooltips(display_text.strip())
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """Maneja la entrada y guarda la respuesta completa para el modal."""
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
            
            # GUARDADO CRÍTICO: Se guarda con metadatos técnicos
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            
            st.rerun() 
            return full_response
