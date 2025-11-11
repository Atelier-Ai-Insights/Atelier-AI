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
    Llama a la API de Gemini con lógica de rotación de claves, reintentos 
    y manejo robusto de respuestas.
    """
    start_index = st.session_state.get("api_key_index", 0)
    num_keys = len(api_keys)
    
    # --- INICIO CORRECCIÓN 1: Lógica de Configuración de Tokens ---
    # 1. Empezar con la config base de config.py
    final_gen_config = generation_config.copy() # Usar .copy() para no modificar el original

    # 2. Aplicar un 'max_output_tokens' alto por defecto SI NO se especifica
    #    en config.py. Esto soluciona el error 'MAX_TOKENS'.
    if 'max_output_tokens' not in final_gen_config:
        final_gen_config['max_output_tokens'] = 8192 # Valor alto por defecto

    # 3. Si se pasa un override (ej. para chat), dejar que sobreescriba todo
    if generation_config_override:
        final_gen_config.update(generation_config_override) # .update() es más limpio
    # --- FIN CORRECCIÓN 1 ---

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
            # --- ¡INICIO DE LA CORRECCIÓN DE TIPO! ---
            # El modelo correcto es 'gemini-1.5-flash'
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config=final_gen_config, 
                safety_settings=final_safety_settings
            )
            # --- ¡FIN DE LA CORRECCIÓN DE TIPO! ---

            # Intentar generar el contenido
            if isinstance(prompt, list):
                response = model.generate_content(prompt)
            else:
                response = model.generate_content([prompt])
            
            # --- INICIO CORRECCIÓN 2: Manejo Robusto de Respuesta ---
            # NO accedas a response.text directamente.
            
            if not response.candidates:
                last_error = "Error API Gemini: La respuesta no tuvo candidatos válidos."
                print(f"ADVERTENCIA: API Key #{current_key_index + 1} falló. Error: {last_error}. Reintentando...")
                continue # Probar siguiente clave

            candidate = response.candidates[0]
            finish_reason_name = candidate.finish_reason.name

            # Caso 1: Éxito (Terminó normalmente)
            if finish_reason_name == "STOP":
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                # Ahora SÍ es seguro acceder a .text
                return html.unescape(response.text) 

            # Caso 2: Cortado por MAX_TOKENS (¡El error que viste!)
            elif finish_reason_name == "MAX_TOKENS":
                st.warning("Advertencia: La respuesta de la IA fue muy larga y ha sido cortada. (MAX_TOKENS)")
                st.session_state.api_key_index = (current_key_index + 1) % num_keys
                # Intentar devolver el texto parcial que sí se generó
                if candidate.content.parts:
                    partial_text = candidate.content.parts[0].text
                    return html.unescape(partial_text) + "\n\n... (Respuesta truncada por MAX_TOKENS)"
                else:
                    last_error = "MAX_TOKENS pero no se encontró contenido parcial."
                    print(f"ADVERTENCIA: API Key #{current_key_index + 1} falló. Error: {last_error}. Reintentando...")
                    continue # Probar siguiente clave
            
            # Caso 3: Bloqueo de seguridad u otra razón
            else:
                last_error = f"Generación detenida por: {finish_reason_name}"
                # Intentar obtener más detalles del bloqueo
                try:
                    if candidate.safety_ratings:
                        last_error += f" | Ratings: {str(candidate.safety_ratings)}"
                except:
                    pass
                
                print(f"ADVERTENCIA: API Key #{current_key_index + 1} falló. Error: {last_error}. Reintentando...")
                continue # Probar siguiente clave
            
            # --- FIN CORRECCIÓN 2 ---

        except Exception as e:
            # Esto ahora capturará errores de red, auth, etc.
            # (El error 'Invalid operation' ya no debería ocurrir)
            last_error = e
            print(f"ADVERTENCIA: API Key #{current_key_index + 1} falló. Error: {e}. Reintentando...")
            # Continuar el bucle para probar la siguiente clave
        
    # Si el bucle termina, todas las claves fallaron
    st.error(f"Error API Gemini: Todas las claves API fallaron. Último error: {last_error}")
    return None
