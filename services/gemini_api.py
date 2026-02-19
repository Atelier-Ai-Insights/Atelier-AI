import streamlit as st
import warnings
import os
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import time
from config import api_keys, generation_config, safety_settings
from services.logger import log_error

# --- BLOQUEO DE ADVERTENCIAS ---
os.environ["GRPC_VERBOSITY"] = "ERROR"
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="google.generativeai")

# Usamos el modelo estable actual
MODEL_NAME = "gemini-2.5-flash"

def _configure_gemini(key_index):
    try:
        if not api_keys: return False
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
    
    # --- AJUSTE DE CONFIGURACIÓN MAESTRA ---
    final_gen_config = generation_config.copy()
    
    # 1. Aseguramos el máximo de tokens de salida para evitar cortes
    final_gen_config["max_output_tokens"] = 8192 
    
    # 2. Ajustamos temperatura para análisis más ricos (0.4 es ideal para consultoría)
    if "temperature" not in final_gen_config:
        final_gen_config["temperature"] = 0.4
    
    if gen_config: final_gen_config.update(gen_config)
    
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

            # Pequeña pausa para mitigar el Rate Limit en ráfagas
            time.sleep(0.2) 

            content_payload = prompt if isinstance(prompt, list) else [prompt]
            response = model.generate_content(content_payload, stream=stream)
            
            if stream:
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return _stream_generator_wrapper(response)
            
            text_res = response.text
            _save_token_usage(response)
            st.session_state.api_key_index = (current_key_index + 1) % num_keys
            return text_res

        except Exception as e:
            error_str = str(e).lower()
            last_error = e
            # Reintentar en errores comunes de saturación
            if any(x in error_str for x in ["429", "500", "503", "quota", "overloaded"]):
                continue
            break 

    if not stream:
        st.error(f"Error de conexión IA: {str(last_error)[:150]}")
        return None

def _stream_generator_wrapper(response_stream):
    """Generador que maneja de forma segura los fragmentos de la respuesta"""
    try:
        for chunk in response_stream:
            try:
                # El acceso a chunk.text puede fallar si el filtro de seguridad se activa a mitad del stream
                if chunk.text: 
                    yield chunk.text
            except (ValueError, IndexError):
                # Si un fragmento es bloqueado, saltamos al siguiente en lugar de romper el stream
                continue
    except Exception as e:
        yield f"\n\n[Nota: La conexión se interrumpió. Intenta ser más específico en tu consulta. Detalle: {str(e)}]"
