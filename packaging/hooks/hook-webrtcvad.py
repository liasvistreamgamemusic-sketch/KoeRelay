# webrtcvad-wheels は import 名 'webrtcvad' でモジュールを提供するが、配布メタデータ名は
# 'webrtcvad-wheels'。PyInstaller 同梱の contrib フック(hook-webrtcvad.py)は
# copy_metadata('webrtcvad') をハードコードしており PackageNotFoundError で失敗する。
# hookspath のユーザーフックは同梱フックを上書きするので、ここでメタデータ名の差異を吸収する。
from PyInstaller.utils.hooks import copy_metadata

datas = []
for dist in ("webrtcvad-wheels", "webrtcvad"):
    try:
        datas = copy_metadata(dist)
        break
    except Exception:
        continue
