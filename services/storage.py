import streamlit as st
import boto3
import json
import os  # <--- IMPORTANTE: Necesario para leer variables de Railway
import datetime
from utils import normalize_text
from services.logger import log_error

# ==========================================
# FUNCIÓN DE SEGURIDAD PARA VARIABLES
# ==========================================
def get_secret(key):
    """
    Busca la clave primero en las Variables de Entorno (Railway).
    Si no la encuentra, la busca en st.secrets (Local/Streamlit Cloud).
    """
    value = os.environ.get(key)
    if not value:
        try:
            value = st.secrets[key]
        except:
            return None
    return value

@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    """
    Carga la base de datos principal desde S3.
    """
    try:
        endpoint = get_secret("S3_ENDPOINT_URL")
        access_key = get_secret("S3_ACCESS_KEY")
        secret_key = get_secret("S3_SECRET_KEY")
        bucket_name = get_secret("S3_BUCKET")

        if not endpoint or not access_key:
            print("❌ Error Crítico: Faltan variables de entorno S3")
            st.error("Error de configuración: Faltan credenciales de almacenamiento.")
            return []

        s3 = boto3.client(
            "s3", 
            endpoint_url=endpoint, 
            aws_access_key_id=access_key, 
            aws_secret_access_key=secret_key
        )
        
        response = s3.get_object(Bucket=bucket_name, Key="resultado_presentacion (1).json")
        data = json.loads(response["Body"].read().decode("utf-8"))
        
        cliente_norm = normalize_text(cliente or "")
        
        if cliente_norm not in ["insights-atelier", "generico"]: 
             data = [doc for doc in data if "atelier" in normalize_text(doc.get("cliente", "")) or cliente_norm in normalize_text(doc.get("cliente", ""))]
        
        return data

    except Exception as e: 
        print(f"❌ ERROR S3: {str(e)}")
        st.error(f"Error de conexión con el repositorio (S3).")
        log_error("Fallo crítico al cargar base de datos S3", module="Storage", error=e, level="CRITICAL")
        return []

# ==========================================
# REGISTRO DE EVENTOS (AUDITORÍA) - VERSIÓN MAESTRA
# ==========================================
def log_query_event(event_description, mode="General", *args, **kwargs):
    """
    Versión blindada: Acepta 'mode' por posición o nombre. 
    '*args' y '**kwargs' absorben cualquier parámetro inesperado para evitar TypeErrors.
    """
    try:
        from services.supabase_db import supabase

        user_id = st.session_state.get("user_id", "unknown_user")
        client_name = st.session_state.get("cliente", "unknown_client")

        # Resolvemos el modo priorizando el parámetro nombrado (kwargs)
        final_mode = kwargs.get("mode", mode)

        data = {
            "user_id": user_id,
            "cliente": client_name,
            "description": event_description,
            "mode": final_mode,
            "created_at": datetime.datetime.now().isoformat()
        }

        if supabase:
            try:
                supabase.table("activity_logs").insert(data).execute()
            except:
                pass
        
        # Log de consola para Railway
        print(f"🕒 LOG [{final_mode}]: {event_description} by {user_id}")

    except Exception as e:
        print(f"⚠️ Error al registrar evento: {e}")
