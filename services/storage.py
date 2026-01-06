import streamlit as st
import boto3
import json
import os  # <--- IMPORTANTE: Necesario para leer variables de Railway
from utils import normalize_text
# --- ¡NUEVA IMPORTACIÓN! ---
from services.logger import log_error

# ==========================================
# FUNCIÓN DE SEGURIDAD PARA VARIABLES
# ==========================================
def get_secret(key):
    """
    Busca la clave primero en las Variables de Entorno (Railway).
    Si no la encuentra, la busca en st.secrets (Local/Streamlit Cloud).
    """
    # 1. Intento Railway (Environment Variable)
    value = os.environ.get(key)
    # 2. Intento Local (secrets.toml)
    if not value:
        try:
            value = st.secrets[key]
        except:
            return None
    return value

@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    try:
        # --- OBTENER CREDENCIALES DE FORMA SEGURA ---
        endpoint = get_secret("S3_ENDPOINT_URL")
        access_key = get_secret("S3_ACCESS_KEY")
        secret_key = get_secret("S3_SECRET_KEY")
        bucket_name = get_secret("S3_BUCKET")

        # Validación para evitar errores feos si faltan variables
        if not endpoint or not access_key:
            print("❌ Error Crítico: Faltan variables de entorno S3")
            st.error("Error de configuración: Faltan credenciales de almacenamiento.")
            return []

        # --- CONEXIÓN ---
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
        # --- ¡LOGGING MEJORADO! ---
        # Imprimimos el error en la consola de Railway para que puedas verlo en "View Logs" si falla
        print(f"❌ ERROR S3: {str(e)}")
        
        st.error(f"Error de conexión con el repositorio (S3).")
        log_error("Fallo crítico al cargar base de datos S3", module="Storage", error=e, level="CRITICAL")
        return []
