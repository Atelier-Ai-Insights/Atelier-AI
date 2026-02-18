import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """Muestra el historial limpio pero mantiene los datos para el modal."""
    if not history: return

    for msg in history:
        role = msg["role"]
        content = msg["content"] # Dato original sagrado
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # LIMPIEZA VISUAL SUAVE:
                # Solo ocultamos lo que viene después de la metadata técnica |||
                display_text = re.split(r'\|\|\|', content)[0]
                
                # Opcional: Ocultar lista de fuentes explícita si la IA la escribió al final
                display_text = re.split(r'\n\s*Fuentes:', display_text, flags=re.IGNORECASE)[0]
                
                html_content = process_text_with_tooltips(display_text.strip())
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """Guarda la respuesta completa para asegurar que el modal funcione."""
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
            
            # GUARDADO CRÍTICO
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success: on_generation_success(full_response)
            
            st.rerun()
