import os

from supabase import create_client, Client


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


# ---------------------------------------------------------------------------
# Capturas
# ---------------------------------------------------------------------------

def create_capture(capture_id, created_at, user_agent=None, device_id=None,
                   page_key="index", display_name=None):
    response = (
        supabase.table("captures")
        .insert({
            "capture_id": capture_id,
            "created_at": created_at,
            "user_agent": user_agent,
            "device_id": device_id,
            "page_key": page_key,
            "display_name": display_name,
        })
        .select("*")
        .execute()
    )
    if not response.data:
        raise RuntimeError("Não foi possível criar a captura.")
    return response.data[0]


def get_capture(capture_id):
    response = (
        supabase.table("captures")
        .select("*")
        .eq("capture_id", capture_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_capture_by_device(device_id, page_key):
    if not device_id:
        return None
    response = (
        supabase.table("captures")
        .select("*")
        .eq("device_id", device_id)
        .eq("page_key", page_key)
        .order("id", desc=False)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_captures(page_key=None):
    """Lista somente metadados. Contagens e mídias são carregadas sob demanda."""
    query = (
        supabase.table("captures")
        .select("capture_id,created_at,user_agent,device_id,page_key,display_name")
    )
    if page_key:
        query = query.eq("page_key", page_key)
    response = query.order("id", desc=True).execute()
    return response.data or []


def rename_capture(capture_id, display_name):
    response = (
        supabase.table("captures")
        .update({"display_name": display_name})
        .eq("capture_id", capture_id)
        .select("*")
        .execute()
    )
    return response.data[0] if response.data else None


def delete_capture_records(capture_id):
    """Apaga os registros relacionados; os arquivos do Storage são apagados antes."""
    supabase.table("photos").delete().eq("capture_id", capture_id).execute()
    supabase.table("locations").delete().eq("capture_id", capture_id).execute()
    supabase.table("captures").delete().eq("capture_id", capture_id).execute()


# ---------------------------------------------------------------------------
# Localizações
# ---------------------------------------------------------------------------

def create_location(capture_id, latitude, longitude, accuracy, created_at):
    response = (
        supabase.table("locations")
        .insert({
            "capture_id": capture_id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "created_at": created_at,
        })
        .select("*")
        .execute()
    )
    if not response.data:
        raise RuntimeError("Não foi possível registrar a localização.")
    return response.data[0]


def get_recent_locations(capture_id, limit=200):
    """Limita o mapa aos pontos recentes para manter a interface fluida."""
    response = (
        supabase.table("locations")
        .select("id,capture_id,latitude,longitude,accuracy,created_at")
        .eq("capture_id", capture_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(response.data or []))


def get_last_location(capture_id):
    response = (
        supabase.table("locations")
        .select("id,capture_id,latitude,longitude,accuracy,created_at")
        .eq("capture_id", capture_id)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_location_count(capture_id):
    response = (
        supabase.table("locations")
        .select("id", count="exact")
        .eq("capture_id", capture_id)
        .limit(1)
        .execute()
    )
    return response.count or 0


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------

def create_photo(capture_id, location_id, filename, created_at):
    response = (
        supabase.table("photos")
        .insert({
            "capture_id": capture_id,
            "location_id": location_id,
            "filename": filename,
            "created_at": created_at,
        })
        .select("*")
        .execute()
    )
    if not response.data:
        raise RuntimeError("Não foi possível registrar a fotografia.")
    return response.data[0]


def get_photo_page(capture_id, before_id=None, limit=24):
    """Retorna uma página de fotos, das mais recentes para as mais antigas."""
    query = (
        supabase.table("photos")
        .select("id,capture_id,location_id,filename,created_at")
        .eq("capture_id", capture_id)
    )
    if before_id is not None:
        query = query.lt("id", before_id)
    response = query.order("id", desc=True).limit(limit + 1).execute()
    rows = response.data or []
    return rows[:limit], len(rows) > limit


def get_photo_count(capture_id):
    response = (
        supabase.table("photos")
        .select("id", count="exact")
        .eq("capture_id", capture_id)
        .limit(1)
        .execute()
    )
    return response.count or 0


def get_photo_filenames(capture_id):
    response = (
        supabase.table("photos")
        .select("filename")
        .eq("capture_id", capture_id)
        .execute()
    )
    return [row["filename"] for row in (response.data or [])]


def get_photo_by_filename(filename):
    response = (
        supabase.table("photos")
        .select("id,capture_id,filename")
        .eq("filename", filename)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def remove_photo_files(filenames):
    if filenames:
        supabase.storage.from_("captures").remove(filenames)


# ---------------------------------------------------------------------------
# Usuários do painel
# ---------------------------------------------------------------------------

def get_dashboard_user(username):
    response = (
        supabase.table("dashboard_users")
        .select("id,username,password_hash,page_key,is_admin,active,created_at")
        .eq("username", username)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_dashboard_user_by_id(user_id):
    response = (
        supabase.table("dashboard_users")
        .select("id,username,page_key,is_admin,active")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def list_dashboard_users():
    response = (
        supabase.table("dashboard_users")
        .select("id,username,page_key,is_admin,active,created_at")
        .order("username")
        .execute()
    )
    return response.data or []


def create_dashboard_user(username, password_hash, page_key):
    response = (
        supabase.table("dashboard_users")
        .insert({
            "username": username,
            "password_hash": password_hash,
            "page_key": page_key,
            "is_admin": False,
            "active": True,
        })
        .select("id,username,page_key,is_admin,active,created_at")
        .execute()
    )
    if not response.data:
        raise RuntimeError("Não foi possível criar o usuário.")
    return response.data[0]


def delete_dashboard_user(user_id):
    supabase.table("dashboard_users").delete().eq("id", user_id).execute()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def upload_photo(file_data, filename, content_type="image/jpeg"):
    return (
        supabase.storage.from_("captures").upload(
            filename,
            file_data,
            {"content-type": content_type, "upsert": "false"},
        )
    )


def download_photo(filename):
    return supabase.storage.from_("captures").download(filename)
