import streamlit as st
import google.generativeai as genai
from google.generativeai.types import generation_types
import html
import time
import os
from config import api_keys, generation_config, safety_settings
from services.logger import log_error, log_action 

# ==========================================
# CONFIGURACIÓN DE MODELO
# ==========================================

# Usamos 1.5-flash que es el estándar actual rápido y soporta 8k+ tokens de salida
MODEL_NAME = "gemini-1.5-flash"

def _configure_gemini(key_index):
    try:
        if not api_keys: return False
        # Asegurar índice válido para rotación de llaves
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
    
    # --- APLICACIÓN DE LA MEJORA DE TOKENS ---
    # Copiamos la config base y forzamos 8192 tokens para evitar cortes en reportes
    final_gen_config = generation_config.copy()
    
    # Aseguramos que tenga capacidad máxima de escritura
    final_gen_config["max_output_tokens"] = 8192 
    
    if gen_config: 
        final_gen_config.update(gen_config) 
    
    final_safety = safety if safety is not None else safety_settings 
    
    last_error = None
    
    # 2. LÓGICA DE INTENTOS (Round Robin por las llaves disponibles)
    for i in range(num_keys):
        current_key_index = (start_index + i) % num_keys
        
        # Configurar la llave actual
        if not _configure_gemini(current_key_index): continue 

        try:
            model = genai.GenerativeModel(
                model_name=MODEL_NAME, 
                generation_config=final_gen_config, 
                safety_settings=final_safety
            )

            # Pausa de seguridad para evitar Rate Limiting agresivo
            time.sleep(0.5) 

            # Manejo de prompt (lista o string)
            content_payload = prompt if isinstance(prompt, list) else [prompt]
            
            # Llamada a la API
            response = model.generate_content(content_payload, stream=stream)
            
            # --- STREAMING ---
            if stream:
                # Si conecta, retornamos el generador y rotamos la llave para la próxima vez
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                return _stream_generator_wrapper(response)
            
            # --- NO STREAMING ---
            if not response.candidates:
                last_error = "Respuesta vacía o bloqueada por filtros de seguridad."
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
            
            # Si es error 429 (Cuota Excedida), probamos la siguiente llave inmediatamente
            if "429" in error_str or "quota" in error_str or "resource exhausted" in error_str:
                log_error(f"Key #{current_key_index} agotada. Rotando a la siguiente...", module="GeminiAPI", level="WARNING")
                continue
            
            # Si es otro error (ej. Prompt inválido), NO reintentamos
            log_error(f"Error técnico Key #{current_key_index}: {e}", module="GeminiAPI")
            break 

    # Si salimos del bucle sin éxito:
    if not stream:
        st.error(f"No se pudo completar la solicitud. Detalle: {str(last_error)[:150]}...")
        return None

def _stream_generator_wrapper(response_stream):
    """Generador seguro que captura errores durante el streaming."""
    try:
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        # Si se corta a mitad del stream, enviamos el error visible
        yield f"\n\n[⚠️ Interrupción de red o API: {str(e)}]"
