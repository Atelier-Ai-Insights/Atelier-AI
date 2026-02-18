import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial ultra-limpio. 
    Elimina nombres de archivos y metadatos visuales del chat, 
    pero los mantiene en la variable original para el modal.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"] # Dato original completo
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # --- FILTRO DE INVISIBILIDAD ---
                # 1. Eliminamos el bloque técnico oculto (|||)
                display_text = re.split(r'\|\|\|', content)[0]
                
                # 2. Eliminamos nombres de archivos PDF que queden al final (ej: 20-11-28_In-ATL...)
                display_text = re.split(r'\d{2}-\d{2}-\d{2}_In-ATL_.*?\.pdf', display_text, flags=re.IGNORECASE)[0]
                
                # 3. Eliminamos listas de fuentes explícitas si la IA las redactó
                display_text = re.split(r'\n\s*Fuentes:', display_text, flags=re.IGNORECASE)[0]

                # 4. Quitamos espacios en blanco sobrantes al final
                display_text = display_text.strip()
                
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """Guarda la respuesta completa (con fuentes) para que el botón las encuentre."""
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
            
            # Guardamos la respuesta COMPLETA en el estado para el modal
            st.session_state.mode_state[history_key].append({"role": "assistant", "content": full_response})
            if on_generation_success:
                on_generation_success(full_response)
            
            st.rerun() 
            return full_response
