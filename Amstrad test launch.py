import requests

URL = "http://192.168.2.56:8182/api/launch"
MGL = "/media/fat/games/Amstrad PCW/DEV.mgl"

try:
    resp = requests.post(URL, json={"path": MGL}, timeout=10)
    print("Launch sent. Status:", resp.status_code)
    if resp.text:
        print("Response:", resp.text)
except requests.exceptions.RequestException as e:
    print("Could not reach the MiSTer:", e)