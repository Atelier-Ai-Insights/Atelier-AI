import streamlit as st
import boto3
import json
from utils import normalize_text
# --- ¡NUEVA IMPORTACIÓN! ---
from services.logger import log_error

@st.cache_data(show_spinner=False)
def load_database(cliente: str):
    try:
        s3 = boto3.client("s3", endpoint_url=st.secrets["S3_ENDPOINT_URL"], aws_access_key_id=st.secrets["S3_ACCESS_KEY"], aws_secret_access_key=st.secrets["S3_SECRET_KEY"])
        response = s3.get_object(Bucket=st.secrets.get("S3_BUCKET"), Key="resultado_presentacion (1).json")
        data = json.loads(response["Body"].read().decode("utf-8")); cliente_norm = normalize_text(cliente or "")
        if cliente_norm not in ["insights-atelier", "generico"]: 
             data = [doc for doc in data if "atelier" in normalize_text(doc.get("cliente", "")) or cliente_norm in normalize_text(doc.get("cliente", ""))]
        return data
    except Exception as e: 
        # --- ¡LOGGING MEJORADO! ---
        st.error(f"Error de conexión con el repositorio (S3).")
        log_error("Fallo crítico al cargar base de datos S3", module="Storage", error=e, level="CRITICAL")
        return []
