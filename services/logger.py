import logging
import streamlit as st
import traceback
from services.supabase_db import supabase

# Configuración del logger para consola (Streamlit Cloud Logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AtelierApp")

def log_error(message: str, module: str = "General", error: Exception = None, level: str = "ERROR"):
    """
    Registra errores en consola y persiste en Supabase.
    """
    stack_trace = None
    if error:
        # Extraemos el rastro del error para depuración técnica
        stack_trace = "".join(traceback.format_exception(None, error, error.__traceback__))
        full_message = f"{message} | Error: {str(error)}"
        logger.error(f"[{module}] {full_message}\n{stack_trace}")
    else:
        full_message = message
        logger.warning(f"[{module}] {message}") if level == "WARNING" else logger.error(f"[{module}] {message}")

    # PERSISTENCIA EN SUPABASE
    try:
        # Obtenemos el usuario de la sesión de Atelier
        user_email = st.session_state.get("user", "Anonymous/System")
        
        log_entry = {
            "level": level,
            "message": full_message,
            "user_email": user_email,
            "module": module,
            "stack_trace": stack_trace
        }
        
        # Inserción en la tabla de logs
        supabase.table("error_logs").insert(log_entry).execute()
        
    except Exception as e_db:
        print(f"CRITICAL: Falló el guardado del log en Supabase: {e_db}")

def log_action(message: str, module: str = "General"):
    """
    Registra acciones informativas en consola.
    """
    logger.info(f"[{module}] {message}")
