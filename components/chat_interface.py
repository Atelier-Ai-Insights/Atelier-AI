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
        content = msg["content"] # Contenido íntegro original con metadatos técnicos
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
