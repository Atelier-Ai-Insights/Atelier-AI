import streamlit as st
import google.generativeai as genai
import html
import time
from config import api_keys, generation_config, safety_settings
from services.logger import log_error, log_action 

def _configure_gemini(key_index):
    """Función interna para configurar la API con una clave específica."""
    try:
        api_key = api_keys[key_index]
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        log_error(f"Error configurando API Key #{key_index + 1}", module="GeminiAPI", error=e, level="WARNING")
        return False

def call_gemini_api(prompt, generation_config_override=None, safety_settings_override=None):
    """Llama a la API de Gemini y espera la respuesta completa (NO Streaming)."""
    return _execute_gemini_call(prompt, stream=False, gen_config=generation_config_override, safety=safety_settings_override)

# --- ¡NUEVA FUNCIÓN QUE FALTABA! ---
def call_gemini_stream(prompt, generation_config_override=None, safety_settings_override=None):
    """Llama a la API de Gemini y devuelve un generador para Streaming."""
    return _execute_gemini_call(prompt, stream=True, gen_config=generation_config_override, safety=safety_settings_override)

def _execute_gemini_call(prompt, stream=False, gen_config=None, safety=None):
    """Lógica central unificada para llamadas normales y streaming."""
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    final_gen_config = generation_config.copy() 
    if 'max_output_tokens' not in final_gen_config:
        final_gen_config['max_output_tokens'] = 8192 

    if gen_config:
        final_gen_config.update(gen_config) 

    final_safety_settings = safety_settings 
    if safety is not None:
        final_safety_settings = safety 

    last_error = None

    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        if not _configure_gemini(current_key_index):
            last_error = f"Fallo configuración Key #{current_key_index + 1}"
            continue 

        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash", # Tu modelo validado
                generation_config=final_gen_config, 
                safety_settings=final_safety_settings
            )

            if isinstance(prompt, list):
                response = model.generate_content(prompt, stream=stream)
            else:
                response = model.generate_content([prompt], stream=stream)
            
            # --- MANEJO DE STREAMING ---
            if stream:
                return _stream_generator_wrapper(response, current_key_index, num_keys)
            
            # --- MANEJO NORMAL (NO STREAMING) ---
            if not response.candidates:
                error_msg = "La respuesta de la API no tuvo candidatos válidos."
                log_error(f"Key #{current_key_index + 1}: {error_msg}", module="GeminiAPI", level="WARNING")
                last_error = error_msg
                continue 

            candidate = response.candidates[0]
            finish_reason_name = candidate.finish_reason.name

            if finish_reason_name == "STOP":
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return html.unescape(response.text) 

            elif finish_reason_name == "MAX_TOKENS":
                st.warning("Advertencia: La respuesta fue cortada (MAX_TOKENS).")
                log_action("Respuesta truncada por MAX_TOKENS", module="GeminiAPI")
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                if candidate.content.parts:
                    return html.unescape(candidate.content.parts[0].text) + "\n\n..."
                else:
                    continue
            else:
                last_error = f"Detenido por: {finish_reason_name}"
                log_error(f"Key #{current_key_index + 1}: {last_error}", module="GeminiAPI", level="WARNING")
                continue 

        except Exception as e:
            last_error = e
            log_error(f"Excepción Key #{current_key_index + 1}", module="GeminiAPI", error=e, level="WARNING")
            # Continuar loop
        
    # Si no es stream y todo falló
    if not stream:
        critical_msg = f"Todas las claves fallaron. Error: {last_error}"
        st.error(f"Error API Gemini: {critical_msg}")
        log_error(critical_msg, module="GeminiAPI", level="CRITICAL") 
        return None

def _stream_generator_wrapper(response_stream, key_index, num_keys):
    """Envuelve el stream para manejar errores durante la generación."""
    try:
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
        # Si termina bien, actualizamos la llave
        st.session_state.api_key_index = (key_index + 1) % num_keys
    except Exception as e:
        log_error(f"Error durante Streaming Key #{key_index + 1}", module="GeminiAPI", error=e)
        yield f"\n\n[Error de conexión interrumpida: {str(e)}]"
