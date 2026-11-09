"""Download the models the basic voice needs into models/ (for building from source).

    .venv\\Scripts\\python.exe tools\\get_models.py

Both come from their authors' own Hugging Face pages, under CC BY 4.0:
  models/piper/he_IL-noa-medium.onnx(.json)  https://huggingface.co/thewh1teagle/piper-he-noa
  models/renikud.onnx                        https://huggingface.co/renikud/renikud (model.onnx)
The voice "תאיר" is not part of the public source (see README).
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    ROOT / "models" / "piper" / "he_IL-noa-medium.onnx":
        "https://huggingface.co/thewh1teagle/piper-he-noa/resolve/main/he_IL-noa-medium.onnx",
    ROOT / "models" / "piper" / "he_IL-noa-medium.onnx.json":
        "https://huggingface.co/thewh1teagle/piper-he-noa/resolve/main/he_IL-noa-medium.onnx.json",
    ROOT / "models" / "renikud.onnx": "https://huggingface.co/renikud/renikud/resolve/main/model.onnx",
}

for target, url in FILES.items():
    if target.is_file():
        print("have", target.relative_to(ROOT))
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    print("get ", url)
    urllib.request.urlretrieve(url, target)
print("models ready")
