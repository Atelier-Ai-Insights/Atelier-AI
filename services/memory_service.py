import streamlit as st
from datetime import datetime
from services.supabase_db import supabase

def save_project_insight(content, source_mode="manual"):
    try:
        # Guardamos el contenido tal cual (con HTML y todo)
        data = {
            "content": content,
            "source": source_mode,
            "created_at": datetime.utcnow().isoformat()
        }
        supabase.table("project_memory").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving: {e}")
        return False

def get_project_memory():
    try:
        response = supabase.table("project_memory").select("*").order("created_at", desc=True).limit(20).execute()
        return response.data
    except: return []

def delete_project_memory(pin_id):
    try:
        supabase.table("project_memory").delete().eq("id", pin_id).execute()
        return True
    except: return False
