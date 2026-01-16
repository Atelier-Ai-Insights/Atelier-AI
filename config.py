import streamlit as st
import os

# ==============================
# DEFINICIÓN DE PLANES Y PERMISOS
# ==============================
PLAN_FEATURES = {
    "Explorer": {
        "reports_per_month": 0, "chat_queries_per_day": 4, "projects_per_year": 2,
        "has_report_generation": False, "has_creative_conversation": False,
        "has_concept_generation": False, "has_idea_evaluation": False,
        "has_image_evaluation": False, "has_video_evaluation": False,
        "transcript_file_limit": 1, "ppt_downloads_per_month": 2,
        "project_upload_limit": 1, 
        "text_analysis_max_files_per_project": 1,
        "text_analysis_questions_per_day": 5,
        "da_has_summary": True,
        "da_has_autocode": False,
        "da_has_wordcloud": False,
        "da_has_ppt_export": False,
        "da_has_quick_analysis": True,
        "da_has_pivot_table": False,
        "da_has_correlation": False,
        "da_has_group_comparison": False,
        # --- ETNOCHAT ---
        "has_etnochat_analysis": True,
        "etnochat_project_limit": 1,
        "etnochat_max_files_per_project": 3,
        "etnochat_questions_per_day": 5,
    },
    "Strategist": {
        "reports_per_month": 0, "chat_queries_per_day": float('inf'), "projects_per_year": 10,
        "has_report_generation": False, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": False,
        "has_image_evaluation": False, "has_video_evaluation": False,
        "transcript_file_limit": 5, "ppt_downloads_per_month": 4,
        "project_upload_limit": 2, 
        "text_analysis_max_files_per_project": 4,
        "text_analysis_questions_per_day": 10,
        "da_has_summary": True,
        "da_has_autocode": False,
        "da_has_wordcloud": True,
        "da_has_ppt_export": False,
        "da_has_quick_analysis": True,
        "da_has_pivot_table": True,
        "da_has_correlation": False,
        "da_has_group_comparison": False,
        # --- ETNOCHAT ---
        "has_etnochat_analysis": True,
        "etnochat_project_limit": 3,
        "etnochat_max_files_per_project": 10,
        "etnochat_questions_per_day": 15,
    },
    "Enterprise": {
        "reports_per_month": float('inf'), "chat_queries_per_day": float('inf'), "projects_per_year": float('inf'),
        "has_report_generation": True, "has_creative_conversation": True,
        "has_concept_generation": True, "has_idea_evaluation": True,
        "has_image_evaluation": True, "has_video_evaluation": True,
        "transcript_file_limit": 10, "ppt_downloads_per_month": float('inf'),
        "project_upload_limit": 5, 
        "text_analysis_max_files_per_project": 6,
        "text_analysis_questions_per_day": float('inf'),
        "da_has_summary": True,
        "da_has_autocode": True,
        "da_has_wordcloud": True,
        "da_has_ppt_export": True,
        "da_has_quick_analysis": True,
        "da_has_pivot_table": True,
        "da_has_correlation": True,
        "da_has_group_comparison": True,
        # --- ETNOCHAT ---
        "has_etnochat_analysis": True,
        "etnochat_project_limit": 10,
        "etnochat_max_files_per_project": 25,
        "etnochat_questions_per_day": float('inf'),
    }
}

# ==============================
# CONFIGURACIÓN DE LA API DE GEMINI
# ==============================

def get_secret(key):
    """Obtiene secretos de entorno o st.secrets de forma segura."""
    # 1. Intentar variable de entorno (Prioridad para Railway/Docker)
    value = os.environ.get(key)
    if value: return value
    
    # 2. Intentar st.secrets (Prioridad para Streamlit Cloud)
    try:
        # Verificamos si existe antes de acceder para no lanzar excepción
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except: pass
    
    return None

# Lista de claves
raw_keys = [
    get_secret("API_KEY_1"),
    get_secret("API_KEY_2"),
    get_secret("API_KEY_3")
]

# Filtramos claves vacías
api_keys = [k for k in raw_keys if k is not None]

# Advertencia en consola si no hay claves (para debug)
if not api_keys:
    print("⚠️ ADVERTENCIA: No se encontraron API Keys de Gemini. La IA no funcionará.")

generation_config = {
    "temperature": 0.5, 
    "top_p": 0.8, 
    "top_k": 32, 
    "max_output_tokens": 8192
}

# Configuración base de seguridad (gemini_api.py la sobrescribe con BLOCK_NONE si es necesario)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"}
]

# ==============================
# CONSTANTES GLOBALES
# ==============================
banner_file = "Banner (2).jpg"
