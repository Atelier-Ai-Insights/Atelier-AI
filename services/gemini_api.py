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

def _save_token_usage(response_obj):
    """
    Extrae los metadatos de uso de tokens del objeto de respuesta (Stream o Normal)
    y los guarda en la sesión.
    """
    try:
        # En versiones recientes de la librería, usage_metadata está disponible
        # tanto en respuesta normal como en el objeto stream después de iterarlo.
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
        # Si falla la lectura de metadatos, no bloqueamos la app, solo registramos 0
        st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}

def call_gemini_api(prompt, generation_config_override=None, safety_settings_override=None):
    """Llama a la API de Gemini y espera la respuesta completa (NO Streaming)."""
    return _execute_gemini_call(prompt, stream=False, gen_config=generation_config_override, safety=safety_settings_override)

def call_gemini_stream(prompt, generation_config_override=None, safety_settings_override=None):
    """Llama a la API de Gemini y devuelve un generador para Streaming."""
    return _execute_gemini_call(prompt, stream=True, gen_config=generation_config_override, safety=safety_settings_override)

def _execute_gemini_call(prompt, stream=False, gen_config=None, safety=None):
    """Lógica central unificada."""
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    # Reset de tokens antes de empezar
    st.session_state.last_token_usage = {"prompt_tokens": 0, "candidates_tokens": 0, "total_tokens": 0}
    
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
                model_name="gemini-2.5-flash",
                generation_config=final_gen_config, 
                safety_settings=final_safety_settings
            )

            if isinstance(prompt, list):
                response = model.generate_content(prompt, stream=stream)
            else:
                response = model.generate_content([prompt], stream=stream)
            
            # --- CASO STREAMING ---
            if stream:
                # Pasamos el objeto 'response' completo al wrapper para extraer tokens al final
                return _stream_generator_wrapper(response, current_key_index, num_keys)
            
            # --- CASO NORMAL (NO STREAMING) ---
            if not response.candidates:
                error_msg = "La respuesta de la API no tuvo candidatos válidos."
                log_error(f"Key #{current_key_index + 1}: {error_msg}", module="GeminiAPI", level="WARNING")
                last_error = error_msg
                continue 

            candidate = response.candidates[0]
            finish_reason_name = candidate.finish_reason.name

            if finish_reason_name == "STOP":
                # Capturar tokens
                _save_token_usage(response)
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return html.unescape(response.text) 

            elif finish_reason_name == "MAX_TOKENS":
                st.warning("Advertencia: La respuesta fue cortada (MAX_TOKENS).")
                # Intentar capturar tokens parciales
                _save_token_usage(response)
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
        
    if not stream:
        critical_msg = f"Todas las claves fallaron. Error: {last_error}"
        st.error(f"Error API Gemini: {critical_msg}")
        log_error(critical_msg, module="GeminiAPI", level="CRITICAL") 
        return None

def _stream_generator_wrapper(response_stream, key_index, num_keys):
    """
    Envuelve el stream para manejar errores y capturar tokens AL FINAL.
    """
    try:
        for chunk in response_stream:
            try:
                text_chunk = chunk.text
                if text_chunk:
                    yield text_chunk
            except ValueError:
                pass
            except Exception:
                raise
        
        # --- ¡AQUÍ ES DONDE CAPTURAMOS LOS TOKENS DEL STREAM! ---
        # Una vez el bucle termina, el objeto response_stream tiene los metadatos completos
        _save_token_usage(response_stream)
            
        st.session_state.api_key_index = (key_index + 1) % num_keys
        
    except Exception as e:
        log_error(f"Error durante Streaming Key #{key_index + 1}", module="GeminiAPI", error=e)
        yield f"\n\n[Error de conexión interrumpida: {str(e)}]"
