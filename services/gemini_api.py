import streamlit as st
# --- BLOQUEO DE ADVERTENCIAS PARA EVITAR PANTALLA BLANCA ---
import warnings
import os
# Silenciamos la advertencia de deprecación que cuelga la app
os.environ["GRPC_VERBOSITY"] = "ERROR" # Silencia logs de bajo nivel de Google
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="google.generativeai")
# -----------------------------------------------------------

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
from config import api_keys, generation_config, safety_settings
from services.logger import log_error

# ==========================================
# CONFIGURACIÓN DE MODELO
# ==========================================

# Usamos el modelo estable actual
MODEL_NAME = "gemini-2.5-flash"

def _configure_gemini(key_index):
    try:
        if not api_keys: return False
        # Asegurar índice válido
        idx = key_index % len(api_keys)
        genai.configure(api_key=api_keys[idx])
        return True
    except Exception as e:
        log_error(f"Error Key #{key_index}", module="GeminiAPI", error=e)
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
    except: pass

def call_gemini_api(prompt, generation_config_override=None, safety_settings_override=None):
    return _execute_gemini_call(prompt, stream=False, gen_config=generation_config_override, safety=safety_settings_override)

def call_gemini_stream(prompt, generation_config_override=None, safety_settings_override=None):
    return _execute_gemini_call(prompt, stream=True, gen_config=generation_config_override, safety=safety_settings_override)

def _execute_gemini_call(prompt, stream=False, gen_config=None, safety=None):
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    # Configuración base
    final_gen_config = generation_config.copy()
    final_gen_config["max_output_tokens"] = 8192 
    if gen_config: final_gen_config.update(gen_config)
    
    # Filtros de seguridad permisivos para evitar bloqueos silenciosos
    final_safety = safety if safety is not None else {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    last_error = None
    
    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        if not _configure_gemini(current_key_index): continue 

        try:
            model = genai.GenerativeModel(
                model_name=MODEL_NAME, 
                generation_config=final_gen_config, 
                safety_settings=final_safety
            )

            time.sleep(0.5) # Evitar rate limit

            content_payload = prompt if isinstance(prompt, list) else [prompt]
            
            # Llamada a la API
            response = model.generate_content(content_payload, stream=stream)
            
            if stream:
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return _stream_generator_wrapper(response)
            
            # Validación de respuesta no streaming
            try:
                # Si fue bloqueado, acceder a .text lanza ValueError
                text_res = response.text
            except ValueError:
                last_error = "Respuesta bloqueada por filtros de seguridad."
                continue 

            if not text_res:
                last_error = "Respuesta vacía del servidor."
                continue

            _save_token_usage(response)
            st.session_state.api_key_index = (current_key_index + 1) % num_keys
            return text_res

        except Exception as e:
            error_str = str(e).lower()
            last_error = e
            # Reintentar solo si es error de servidor o cuota
            if any(x in error_str for x in ["429", "500", "503", "quota", "overloaded"]):
                continue
            break # Si es otro error, paramos

    if not stream:
        st.error(f"Error de conexión IA: {str(last_error)[:150]}")
        return None

def _stream_generator_wrapper(response_stream):
    try:
        for chunk in response_stream:
            try:
                if chunk.text: yield chunk.text
            except ValueError: continue
    except Exception as e:
        yield f"\n[Error de red: {str(e)}]"
