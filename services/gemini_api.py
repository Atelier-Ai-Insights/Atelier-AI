import streamlit as st
import google.generativeai as genai
import html
from config import api_keys, generation_config, safety_settings

# (Dejamos fuera la inicialización de st.session_state.api_key_index, 
# eso irá en app_v2.py)

def configure_api_dynamically():
    global api_keys
    index = st.session_state.api_key_index
    try:
        api_key = api_keys[index]; genai.configure(api_key=api_key)
        st.session_state.api_key_index = (index + 1) % len(api_keys)
        print(f"INFO: Usando API Key #{index + 1}")
    except IndexError: st.error(f"Error: Índice API Key ({index}) fuera de rango.")
    except Exception as e: st.error(f"Error config API Key #{index + 1}: {e}")

# Inicializa el modelo aquí
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash", 
    generation_config=generation_config, 
    safety_settings=safety_settings
)

def call_gemini_api(prompt):
    configure_api_dynamically()
    try:
        if isinstance(prompt, list): response = model.generate_content(prompt)
        else: response = model.generate_content([prompt])
        return html.unescape(response.text)
    except Exception as e: 
        print(f"ERROR GEMINI: {e}")
        st.error(f"Error API Gemini (Key #{st.session_state.api_key_index}): {e}. Tipo: {type(prompt)}"); 
        return None
