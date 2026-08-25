import os
from supabase import create_client, Client


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY
)


# ============================================================
# CAPTURES
# ============================================================

def create_capture(capture_id, created_at, user_agent=None):
    response = (
        supabase
        .table("captures")
        .insert({
            "capture_id": capture_id,
            "created_at": created_at,
            "user_agent": user_agent
        })
        .select("id, capture_id, created_at, user_agent")
        .execute()
    )

    if not response.data:
        raise RuntimeError("Não foi possível criar a captura.")

    return response.data[0]


def get_capture(capture_id):
    response = (
        supabase
        .table("captures")
        .select("*")
        .eq("capture_id", capture_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def get_all_captures():
    response = (
        supabase
        .table("captures")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    return response.data or []


# ============================================================
# LOCATIONS
# ============================================================

def create_location(
    capture_id,
    latitude,
    longitude,
    accuracy,
    created_at
):
    response = (
        supabase
        .table("locations")
        .insert({
            "capture_id": capture_id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": accuracy,
            "created_at": created_at
        })
        .select("*")
        .execute()
    )

    if not response.data:
        raise RuntimeError("Não foi possível registrar a localização.")

    return response.data[0]


def get_locations(capture_id, after_id=None):
    query = (
        supabase
        .table("locations")
        .select("*")
        .eq("capture_id", capture_id)
        .order("id")
    )

    if after_id is not None:
        query = query.gt("id", after_id)

    response = query.execute()

    return response.data or []


# ============================================================
# PHOTOS
# ============================================================

def create_photo(
    capture_id,
    location_id,
    filename,
    created_at
):
    response = (
        supabase
        .table("photos")
        .insert({
            "capture_id": capture_id,
            "location_id": location_id,
            "filename": filename,
            "created_at": created_at
        })
        .select("*")
        .execute()
    )

    if not response.data:
        raise RuntimeError("Não foi possível registrar a fotografia.")

    return response.data[0]


def get_photos(capture_id):
    response = (
        supabase
        .table("photos")
        .select("*")
        .eq("capture_id", capture_id)
        .order("id")
        .execute()
    )

    return response.data or []


# ============================================================
# STORAGE
# ============================================================

def upload_photo(file_data, filename, content_type="image/jpeg"):
    response = (
        supabase
        .storage
        .from_("captures")
        .upload(
            filename,
            file_data,
            {
                "content-type": content_type,
                "upsert": "false"
            }
        )
    )

    return response
