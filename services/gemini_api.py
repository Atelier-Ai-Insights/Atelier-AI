import streamlit as st
import google.generativeai as genai
import html
import time
from config import api_keys, generation_config, safety_settings
from services.logger import log_error
# --- NUEVA IMPORTACIÓN: Servicios de Caché ---
from services.semantic_cache import check_semantic_cache, save_to_cache

# ==========================================
# CONFIGURACIÓN DE MODELO
# ==========================================

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
    # Guardamos tokens solo para estadística
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
    
    # ---------------------------------------------------------
    # 1. VERIFICACIÓN DE CACHÉ (OPTIMIZACIÓN DE COSTOS)
    # ---------------------------------------------------------
    # Solo buscamos en caché si es texto plano y no es streaming.
    # (Las listas multimodales con imágenes son complejas de vectorizar por ahora)
    if isinstance(prompt, str) and not stream:
        cached_response = check_semantic_cache(prompt)
        if cached_response:
            # Si encontramos respuesta, la devolvemos inmediatamente (Costo $0)
            st.toast("⚡ Respuesta recuperada de memoria (Cache Hit)", icon="💾")
            return cached_response

    # ---------------------------------------------------------
    # 2. LLAMADA A LA API (SI NO HUBO CACHÉ)
    # ---------------------------------------------------------
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    final_gen_config = generation_config.copy() 
    if gen_config: final_gen_config.update(gen_config) 
    
    final_safety = safety if safety is not None else safety_settings 
    
    last_error = None
    
    # Intentamos rotar llaves si hay error de cuota
    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        # Configurar llave actual
        if not _configure_gemini(current_key_index): continue 

        try:
            model = genai.GenerativeModel(
                model_name=MODEL_NAME, 
                generation_config=final_gen_config, 
                safety_settings=final_safety
            )

            # Pausa técnica para evitar saturación (Rate Limiting propio)
            time.sleep(0.5) 

            # Ejecución
            if isinstance(prompt, list):
                response = model.generate_content(prompt, stream=stream)
            else:
                response = model.generate_content([prompt], stream=stream)
            
            # --- CASO STREAMING ---
            if stream:
                # Si conecta, actualizamos índice y retornamos generador
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return _stream_generator_wrapper(response)
            
            # --- CASO NO STREAMING ---
            if not response.candidates:
                last_error = "Respuesta vacía o bloqueada por filtros de seguridad."
                continue 

            # ÉXITO
            _save_token_usage(response)
            st.session_state.api_key_index = (current_key_index + 1) % num_keys
            
            if response.text:
                final_text = html.unescape(response.text)
                
                # 3. GUARDAR EN CACHÉ PARA EL FUTURO
                # Si la respuesta fue buena, la guardamos para ahorrar en la próxima vez
                if isinstance(prompt, str):
                    save_to_cache(prompt, final_text)
                
                return final_text
            
            return ""

        except Exception as e:
            error_str = str(e).lower()
            last_error = e
            
            # Si es error 429 (Cuota/Quota), rotamos llave inmediatamente
            if "429" in error_str or "quota" in error_str or "resource exhausted" in error_str:
                log_error(f"Key #{current_key_index} agotada. Rotando a la siguiente...", module="GeminiAPI", level="WARNING")
                continue
            
            # Si es otro error (ej. Prompt inválido), no insistimos
            log_error(f"Error técnico Key #{current_key_index}: {e}", module="GeminiAPI")
            break 

    # Si salimos del bucle sin éxito:
    if not stream:
        st.error(f"No se pudo completar la solicitud. Error: {str(last_error)[:150]}...")
        return None

def _stream_generator_wrapper(response_stream):
    """Generador simple para manejar el streaming de texto."""
    try:
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"\n[Interrupción de conexión: {str(e)}]"
