import streamlit as st
import google.generativeai as genai
from google.generativeai.types import generation_types
import html
import time
import random
from config import api_keys, generation_config, safety_settings
from services.logger import log_error, log_action 

# ==========================================
# CONFIGURACIÓN DE MODELO
# ==========================================
# Modelo solicitado: Flash 2.5 (Alta velocidad y eficiencia)
MODEL_NAME = "gemini-2.0-flash" 

def _configure_gemini(key_index):
    """Función interna para configurar la API con una clave específica."""
    try:
        # Rotación segura
        if key_index >= len(api_keys):
            key_index = 0
        api_key = api_keys[key_index]
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        log_error(f"Error configurando API Key #{key_index + 1}", module="GeminiAPI", error=e, level="WARNING")
        return False

def _save_token_usage(response_obj):
    try:
        if hasattr(response_obj, 'usage_metadata'):
            usage = response_obj.usage_metadata
            st.session_state.last_token_usage = {
                "prompt_tokens": usage.prompt_token_count,
                "candidates_tokens": usage.candidates_token_count,
                "total_tokens": usage.total_token_count
            }
        else:
            st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}
    except Exception:
        st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}

def call_gemini_api(prompt, generation_config_override=None, safety_settings_override=None):
    return _execute_gemini_call(prompt, stream=False, gen_config=generation_config_override, safety=safety_settings_override)

def call_gemini_stream(prompt, generation_config_override=None, safety_settings_override=None):
    return _execute_gemini_call(prompt, stream=True, gen_config=generation_config_override, safety=safety_settings_override)

def _execute_gemini_call(prompt, stream=False, gen_config=None, safety=None):
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}
    
    final_gen_config = generation_config.copy() 
    if 'max_output_tokens' not in final_gen_config: final_gen_config['max_output_tokens'] = 8192 
    if gen_config: final_gen_config.update(gen_config) 
    
    final_safety = safety if safety is not None else safety_settings 
    last_error = None

    # --- BUCLE DE INTENTOS (Retries Inteligentes) ---
    # Intentamos hasta 3 veces si hay errores de saturación
    max_retries = 3 
    
    for attempt in range(max_retries + 1):
        
        # Iterar sobre las llaves disponibles (Load Balancing)
        for i in range(num_keys):
            current_key_index = (start_index + i) % num_keys
            
            if not _configure_gemini(current_key_index): continue 

            try:
                model = genai.GenerativeModel(
                    model_name=MODEL_NAME, 
                    generation_config=final_gen_config, 
                    safety_settings=final_safety
                )

                if isinstance(prompt, list):
                    response = model.generate_content(prompt, stream=stream)
                else:
                    response = model.generate_content([prompt], stream=stream)
                
                if stream:
                    return _stream_generator_wrapper(response, current_key_index, num_keys)
                
                if not response.candidates:
                    last_error = "Respuesta bloqueada o vacía."
                    continue 

                # Si llegamos aquí, ¡éxito!
                _save_token_usage(response)
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                
                if response.candidates[0].content.parts:
                    return html.unescape(response.text)
                return ""

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Si es error de cuota (429) o sobrecarga, pasamos a la siguiente llave
                if "429" in error_str or "quota" in error_str or "resource exhausted" in error_str:
                    log_error(f"Key #{current_key_index} saturada (429).", module="GeminiAPI", level="WARNING")
                    continue 
                else:
                    log_error(f"Error Key #{current_key_index}: {e}", module="GeminiAPI")

        # Si fallaron todas las llaves, esperamos un poco antes del siguiente intento general
        if attempt < max_retries:
            wait_time = (2 ** attempt) + random.uniform(0, 1) # Espera: 2s, 4s, 8s...
            time.sleep(wait_time)
        
    # Si después de todos los intentos sigue fallando:
    if not stream:
        # Mensaje amigable al usuario en lugar de error técnico
        if "429" in str(last_error) or "quota" in str(last_error):
             st.error("⚠️ El sistema está recibiendo muchas solicitudes. Por favor, espera 1 minuto e inténtalo de nuevo.")
        else:
             st.error(f"Error de conexión con IA: {last_error}")
        return None

def _stream_generator_wrapper(response_stream, key_index, num_keys):
    full_text = ""
    try:
        for chunk in response_stream:
            try:
                if chunk.candidates and chunk.candidates[0].finish_reason.name == "SAFETY":
                    yield "\n\n[Bloqueado por seguridad]"
                    break
                if chunk.text:
                    full_text += chunk.text
                    yield chunk.text
            except: continue
        try: _save_token_usage(response_stream)
        except: pass
        st.session_state.api_key_index = (key_index + 1) % num_keys
    except Exception as e:
        if "429" in str(e) or "quota" in str(e):
            yield "\n\n[⚠️ Límite de velocidad momentáneo. Reintentando...]"
        else:
            yield f"\n\n[Error: {str(e)}]"
