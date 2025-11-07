import streamlit as st
import google.generativeai as genai
import html
from config import api_keys, generation_config, safety_settings

# (La inicialización del índice sigue en app.py)

def _configure_gemini(key_index):
    """Función interna para configurar la API con una clave específica."""
    try:
        api_key = api_keys[key_index]
        genai.configure(api_key=api_key)
        print(f"INFO: Configurando API Key #{key_index + 1}")
        return True
    except Exception as e:
        print(f"ERROR: Configurando API Key #{key_index + 1}: {e}")
        return False

def call_gemini_api(prompt, generation_config_override=None, safety_settings_override=None):
    """
    Llama a la API de Gemini con lógica de rotación de claves y reintentos.
    """
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    # Determinar la configuración a usar
    final_gen_config = generation_config
    if generation_config_override:
        # Combinar/sobreescribir la configuración base con la específica
        final_gen_config = {**generation_config, **generation_config_override}

    # Determinar los settings de seguridad
    final_safety_settings = safety_settings # Usar los de config.py por defecto
    if safety_settings_override is not None:
        final_safety_settings = safety_settings_override # Usar el override si se provee

    last_error = None

    # Bucle de reintento (una vez por cada clave disponible)
    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        if not _configure_gemini(current_key_index):
            last_error = f"Error al configurar la Clave API #{current_key_index + 1}."
            continue # Intenta con la siguiente clave

        try:
            # --- ¡INICIO DE LA CORRECCIÓN! ---
            # Volvemos al modelo multimodal 'v1beta' (gemini-pro-vision)
            # Este modelo es compatible con todas las funciones de tu app.
            model = genai.GenerativeModel(
                model_name="gemini-pro-vision", # <-- CORREGIDO
                generation_config=final_gen_config, 
                safety_settings=final_safety_settings
            )
            # --- ¡FIN DE LA CORRECCIÓN! ---

            # Intentar generar el contenido
            if isinstance(prompt, list):
                response = model.generate_content(prompt)
            else:
                response = model.generate_content([prompt])
            
            # ¡Éxito! Actualizar el índice para la PRÓXIMA llamada (balanceo)
            st.session_state.api_key_index = (current_key_index + 1) % num_keys
            return html.unescape(response.text)

        except Exception as e:
            last_error = e
            print(f"ADVERTENCIA: API Key #{current_key_index + 1} falló. Error: {e}. Reintentando...")
            # Continuar el bucle para probar la siguiente clave
    
    # Si el bucle termina, todas las claves fallaron
    st.error(f"Error API Gemini: Todas las claves API fallaron. Último error: {last_error}")
    return None