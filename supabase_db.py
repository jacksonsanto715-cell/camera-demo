import os

from supabase import create_client, Client


# ============================================================
# CONFIGURAÇÃO
# ============================================================

SUPABASE_URL = os.environ["SUPABASE_URL"]

SUPABASE_SECRET_KEY = os.environ[
    "SUPABASE_SECRET_KEY"
]


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# CAPTURES
# ============================================================

def create_capture(
    capture_id,
    created_at,
    user_agent=None,
    device_id=None
):

    data = {
        "capture_id": capture_id,
        "created_at": created_at,
        "user_agent": user_agent,
        "device_id": device_id
    }

    response = (
        supabase
        .table("captures")
        .insert(data)
        .select("*")
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Não foi possível criar a captura."
        )

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


def get_capture_by_device(device_id):

    if not device_id:
        return None

    response = (
        supabase
        .table("captures")
        .select("*")
        .eq("device_id", device_id)
        .order("id", desc=False)
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
        .order("id", desc=True)
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
        raise RuntimeError(
            "Não foi possível registrar a localização."
        )

    return response.data[0]


def get_locations(
    capture_id,
    after_id=None
):

    query = (
        supabase
        .table("locations")
        .select("*")
        .eq("capture_id", capture_id)
    )

    if after_id is not None:
        query = query.gt(
            "id",
            after_id
        )

    response = (
        query
        .order("id", desc=False)
        .execute()
    )

    return response.data or []


def get_last_location(capture_id):

    response = (
        supabase
        .table("locations")
        .select("*")
        .eq("capture_id", capture_id)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


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

            "capture_id":
                capture_id,

            "location_id":
                location_id,

            "filename":
                filename,

            "created_at":
                created_at

        })
        .select("*")
        .execute()
    )

    if not response.data:
        raise RuntimeError(
            "Não foi possível registrar a fotografia."
        )

    return response.data[0]


def get_photos(capture_id):

    response = (
        supabase
        .table("photos")
        .select("*")
        .eq("capture_id", capture_id)
        .order("id", desc=False)
        .execute()
    )

    return response.data or []


def get_photo_location(location_id):

    if location_id is None:
        return None

    response = (
        supabase
        .table("locations")
        .select(
            "id, latitude, longitude, accuracy, created_at"
        )
        .eq("id", location_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


# ============================================================
# STORAGE
# ============================================================

def upload_photo(
    file_data,
    filename,
    content_type="image/jpeg"
):

    return (
        supabase
        .storage
        .from_("captures")
        .upload(

            filename,

            file_data,

            {
                "content-type":
                    content_type,

                "upsert":
                    "false"
            }

        )
    )


def download_photo(filename):

    return (
        supabase
        .storage
        .from_("captures")
        .download(
            filename
        )
    )
