import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial aplicando limpieza visual quirúrgica.
    Mantiene la integridad para el botón de referencias.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"] 
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # --- FILTRO DE INVISIBILIDAD SEGURO ---
                # Usamos una partición simple en lugar de regex split masivos para evitar cortes accidentales
                #
                display_text = content.split('|||')[0]
                
                # Eliminamos la sección de fuentes duplicadas solo si aparece al final del bloque limpio
                #
                display_text = re.sub(r'\n\s*(\*\*|##)?\s*(Fuentes|Referencias|Bibliografía).*$', '', display_text, flags=re.IGNORECASE | re.DOTALL)
                
                display_text = display_text.strip()
                
                # Renderizado con el blindaje de corchetes de utils.py
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Orquestador de interacción: captura la respuesta robusta sin interrupciones.
   
    """
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        full_response = ""
        placeholder = st.empty()
        
        # El generador ya viene configurado para 8,192 tokens
        stream = response_generator_func()
        
        if stream:
            for chunk in stream:
                full_response += chunk
                
                # Durante el streaming, solo ocultamos el separador técnico ||| 
                # para que el usuario no vea los metadatos
                clean_display = full_response.split('|||')[0]
                placeholder.markdown(clean_display + "▌")
            
            # GUARDADO ÍNTEGRO: Crucial para el botón 'Ver Fuentes'
            st.session_state.mode_state[history_key].append({
                "role": "assistant", 
                "content": full_response
            })
            
            if on_generation_success:
                on_generation_success(full_response)
            
            # Estabilización final
            st.rerun() 
            return full_response
