import logging
import streamlit as st
import traceback
from services.supabase_db import supabase

# Configuración básica del logger de Python (para consola)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("AtelierApp")

def log_error(message: str, module: str = "General", error: Exception = None, level: str = "ERROR"):
    """
    Registra un error en la consola y lo guarda en Supabase error_logs.
    """
    # 1. Log en consola (Streamlit Cloud logs)
    if error:
        # Obtener el stack trace completo si hay una excepción
        stack_trace = "".join(traceback.format_exception(None, error, error.__traceback__))
        full_message = f"{message} | Error: {str(error)}"
        logger.error(f"[{module}] {full_message}\n{stack_trace}")
    else:
        stack_trace = None
        full_message = message
        if level == "WARNING":
            logger.warning(f"[{module}] {message}")
        else:
            logger.error(f"[{module}] {message}")

    # 2. Guardar en Supabase (Persistencia)
    try:
        # Intentar obtener el usuario actual, si existe
        user_email = st.session_state.user if "user" in st.session_state else "Anonymous/System"
        
        log_entry = {
            "level": level,
            "message": full_message,
            "user_email": user_email,
            "module": module,
            "stack_trace": stack_trace
        }
        
        # Insertar de forma asíncrona (fire and forget) para no bloquear la UI
        supabase.table("error_logs").insert(log_entry).execute()
        
    except Exception as e_db:
        # Si falla el log a la DB, al menos imprimirlo en consola
        print(f"CRITICAL: Falló el guardado del log en Supabase: {e_db}")

def log_action(message: str, module: str = "General"):
    """
    Registra una acción informativa (solo consola, o ampliar a DB si se desea).
    """
    logger.info(f"[{module}] {message}")
