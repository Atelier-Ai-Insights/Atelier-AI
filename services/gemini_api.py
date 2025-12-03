import streamlit as st
import google.generativeai as genai
from google.generativeai.types import generation_types
import html
import time
from config import api_keys, generation_config, safety_settings
from services.logger import log_error, log_action 

# ==========================================
# CONFIGURACIÓN DE MODELO
# ==========================================
# Usar Flash es correcto por precio, pero el código debe ser estricto.
MODEL_NAME = "gemini-1.5-flash" 

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
    # Guardamos tokens solo para estadística, no afecta facturación
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
    # 1. PREPARACIÓN
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    final_gen_config = generation_config.copy() 
    if gen_config: final_gen_config.update(gen_config) 
    
    final_safety = safety if safety is not None else safety_settings 
    
    # 2. LÓGICA CONSERVADORA (Solo 1 vuelta por las llaves)
    # Eliminamos el bucle "for attempt in range(3)" que multiplicaba el consumo.
    
    last_error = None
    
    # Solo intentamos cada llave UNA vez. Si tienes 3 llaves, máximo 3 intentos totales.
    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        # Configurar
        if not _configure_gemini(current_key_index): continue 

        try:
            model = genai.GenerativeModel(
                model_name=MODEL_NAME, 
                generation_config=final_gen_config, 
                safety_settings=final_safety
            )

            # Pausa de seguridad (Rate Limiting propio)
            # Esperamos 0.5 segundos antes de llamar para no saturar
            time.sleep(0.5) 

            if isinstance(prompt, list):
                response = model.generate_content(prompt, stream=stream)
            else:
                response = model.generate_content([prompt], stream=stream)
            
            # --- STREAMING ---
            if stream:
                # Si conecta, retornamos el generador y actualizamos el índice para rotar carga
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return _stream_generator_wrapper(response)
            
            # --- NO STREAMING ---
            if not response.candidates:
                last_error = "Respuesta vacía o bloqueada."
                continue # Prueba siguiente llave

            # ÉXITO
            _save_token_usage(response)
            st.session_state.api_key_index = (current_key_index + 1) % num_keys
            
            if response.text:
                return html.unescape(response.text)
            return ""

        except Exception as e:
            error_str = str(e).lower()
            last_error = e
            
            # Si es error 429 (Cuota), probamos la siguiente llave inmediatamente
            if "429" in error_str or "quota" in error_str:
                log_error(f"Key #{current_key_index} llena. Rotando...", module="GeminiAPI", level="WARNING")
                continue
            
            # Si es otro error (ej. Prompt inválido), NO reintentamos para no quemar recursos en bucle
            log_error(f"Error técnico Key #{current_key_index}: {e}", module="GeminiAPI")
            break # ROMPEMOS EL BUCLE. Si el prompt está mal, está mal en todas las llaves.

    # Si salimos del bucle sin éxito:
    if not stream:
        st.error(f"No se pudo completar la solicitud. Error: {str(last_error)[:100]}...")
        return None

def _stream_generator_wrapper(response_stream):
    """Generador simple sin reintentos internos."""
    try:
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"\n[Corte de conexión: {str(e)}]"
