import urllib.request
import json
import threading
from version_info import VERSION, GITHUB_UPDATE_URL

def check_for_updates_thread(callback):
    """
    Runs check_for_updates in a separate thread and calls callback(result).
    result is (has_update, new_version, error_msg)
    """
    def run():
        res = check_for_updates()
        callback(res)
        
    threading.Thread(target=run, daemon=True).start()

def check_for_updates():
    """
    Checks the GITHUB_UPDATE_URL for a version.json.
    Expected Format: {"version": "x.y.z", "url": "..."}
    Returns: (has_update, new_version, error_msg)
    """
    if "VOTRE_USER" in GITHUB_UPDATE_URL:
        return (False, None, "URL non configurée")

    try:
        with urllib.request.urlopen(GITHUB_UPDATE_URL, timeout=3) as url:
            data = json.loads(url.read().decode())
            remote_version = data.get("version")
            
            if is_newer(remote_version, VERSION):
                return (True, remote_version, None)
            else:
                return (False, remote_version, None)
                
    except Exception as e:
        return (False, None, str(e))

def is_newer(remote, local):
    try:
        r_parts = [int(p) for p in remote.split('.')]
        l_parts = [int(p) for p in local.split('.')]
        return r_parts > l_parts
    except:
        return False
