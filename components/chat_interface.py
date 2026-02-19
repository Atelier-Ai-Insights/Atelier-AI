import streamlit as st
import re
from utils import process_text_with_tooltips

def render_chat_history(history, source_mode="chat"):
    """
    Renderiza el historial con el estándar de invisibilidad sistemática. 
    Mantiene la integridad de los datos para el botón de referencias.
    """
    if not history:
        return

    for msg in history:
        role = msg["role"]
        content = msg["content"] 
        avatar = "✨" if role == "assistant" else "👤"
        
        with st.chat_message(role, avatar=avatar):
            if role == "assistant":
                # --- FILTRO DE INVISIBILIDAD SISTEMÁTICA ---
                # 1. Separamos el contenido analítico de los metadatos técnicos
                display_text = re.split(r'\|\|\|', content)[0]
                
                # 2. Eliminamos rastro de archivos con prefijos técnicos (In-ATL_)
                display_text = re.split(r'\d{2,4}-\d{1,2}-\d{1,2}_In-ATL_.*?\.pdf', display_text, flags=re.IGNORECASE)[0]
                
                # 3. Eliminamos secciones de fuentes duplicadas que ensucian el chat
                display_text = re.split(r'\n\s*(\*\*|##)?\s*(Fuentes|Referencias|Bibliografía)', display_text, flags=re.IGNORECASE)[0]

                # 4. Limpieza de seguridad para asegurar que no queden corchetes técnicos vacíos
                display_text = display_text.strip()
                
                # Renderizado con Tooltips inteligentes
                html_content = process_text_with_tooltips(display_text)
                st.markdown(html_content, unsafe_allow_html=True)
            else:
                st.markdown(content)

def handle_chat_interaction(prompt, response_generator_func, history_key, source_mode, on_generation_success=None):
    """
    Orquestador de interacción: garantiza que la respuesta robusta 
    se capture íntegramente antes del renderizado visual.
    """
    # Guardamos la consulta del usuario en el estado del modo actual
    st.session_state.mode_state[history_key].append({"role": "user", "content": prompt})
    
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="✨"):
        full_response = ""
        # Placeholder para el efecto de escritura (streaming)
        placeholder = st.empty()
        
        # Llamada al motor de IA optimizado para 8,192 tokens
        stream = response_generator_func()
        
        if stream:
            for chunk in stream:
                full_response += chunk
                # Visualización progresiva (Solo mostramos el texto limpio durante el stream)
                clean_chunk_display = re.split(r'\|\|\|', full_response)[0]
                placeholder.markdown(clean_chunk_display + "▌")
            
            # GUARDADO MAESTRO: Preservamos la cadena completa con separadores técnicos
            # Esto es lo que permite que el modal extraiga las fuentes únicas.
            st.session_state.mode_state[history_key].append({
                "role": "assistant", 
                "content": full_response
            })
            
            if on_generation_success:
                on_generation_success(full_response)
            
            # Forzamos refresco para estabilizar la UI y mostrar la barra de acciones final
            st.rerun() 
            return full_response
