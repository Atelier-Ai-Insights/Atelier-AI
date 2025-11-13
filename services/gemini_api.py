import streamlit as st
import google.generativeai as genai
import html
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
    """
    Llama a la API de Gemini con lógica de rotación de claves y logging robusto.
    """
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    final_gen_config = generation_config.copy() 
    if 'max_output_tokens' not in final_gen_config:
        final_gen_config['max_output_tokens'] = 8192 

    if generation_config_override:
        final_gen_config.update(generation_config_override) 

    final_safety_settings = safety_settings 
    if safety_settings_override is not None:
        final_safety_settings = safety_settings_override 

    last_error = None

    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        if not _configure_gemini(current_key_index):
            last_error = f"Fallo configuración Key #{current_key_index + 1}"
            continue 

        try:
            # --- ¡CORRECCIÓN AQUÍ! Usamos la versión específica ---
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash-001", 
                generation_config=final_gen_config, 
                safety_settings=final_safety_settings
            )

            if isinstance(prompt, list):
                # Para EtnoChat (multimodal)
                response = model.generate_content(prompt)
            else:
                # Para texto normal
                response = model.generate_content([prompt])
            
            if not response.candidates:
                error_msg = "La respuesta de la API no tuvo candidatos válidos."
                log_error(f"Intento fallido Key #{current_key_index + 1}: {error_msg}", module="GeminiAPI", level="WARNING")
                last_error = error_msg
                continue 

            candidate = response.candidates[0]
            finish_reason_name = candidate.finish_reason.name

            if finish_reason_name == "STOP":
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return html.unescape(response.text) 

            elif finish_reason_name == "MAX_TOKENS":
                st.warning("Advertencia: La respuesta de la IA fue muy larga y ha sido cortada. (MAX_TOKENS)")
                log_action("Respuesta truncada por MAX_TOKENS", module="GeminiAPI")
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                if candidate.content.parts:
                    partial_text = candidate.content.parts[0].text
                    return html.unescape(partial_text) + "\n\n... (Respuesta truncada por MAX_TOKENS)"
                else:
                    last_error = "MAX_TOKENS sin contenido parcial."
                    log_error(f"Key #{current_key_index + 1}: {last_error}", module="GeminiAPI", level="WARNING")
                    continue 
            
            else:
                last_error = f"Generación detenida por: {finish_reason_name}"
                try:
                    if candidate.safety_ratings:
                        last_error += f" | Ratings: {str(candidate.safety_ratings)}"
                except: pass
                
                log_error(f"Key #{current_key_index + 1} bloqueada/fallida: {last_error}", module="GeminiAPI", level="WARNING")
                continue 

        except Exception as e:
            last_error = e
            log_error(f"Excepción en Key #{current_key_index + 1}", module="GeminiAPI", error=e, level="WARNING")
            # Continuar el bucle
        
    # Si llegamos aquí, todas fallaron
    critical_msg = f"Todas las claves API fallaron. Último error: {last_error}"
    st.error(f"Error API Gemini: {critical_msg}")
    log_error(critical_msg, module="GeminiAPI", level="CRITICAL") 
    return None
