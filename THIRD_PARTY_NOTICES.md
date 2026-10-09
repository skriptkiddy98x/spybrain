# Third-party components

Copyright and licenses of the components remain with their authors. License texts from the installed distributions are in `licenses/`, and for bundled libraries also in `_internal/`. This file grants no new license to the user's original project.

| Component | Version | Source |
|---|---|---|
| Qt for Python / PySide6 Essentials | 6.12.0 | https://code.qt.io/pyside/pyside-setup.git/ |
| Python | 3.13.15 | https://www.python.org/downloads/source/ |
| Sherlock | 0.16.2 | https://github.com/sherlock-project/sherlock |
| Maigret | 0.6.6 | https://github.com/soxoj/maigret |
| theHarvester | 4.11.1 | https://github.com/laramies/theHarvester |
| PhoneInfoga | 2.11.0, commit 5f6156f | https://github.com/sundowndev/phoneinfoga/tree/v2.11.0 |
| phonenumbers | 9.0.41 | https://github.com/daviddrysdale/python-phonenumbers |
| ExifRead | 3.5.1 | https://github.com/ianare/exif-py |
| Pillow | 12.3.0 | https://github.com/python-pillow/Pillow |
| dnspython | 2.8.0 | https://github.com/rthalley/dnspython |
| psutil | 7.2.2 | https://github.com/giampaolo/psutil |
| GeoCLIP | 1.2.3 | https://github.com/VicenteVivan/geo-clip |
| PyTorch / torchvision | 2.14.1 / 0.29.1 | https://github.com/pytorch/pytorch |
| Hugging Face transformers / tokenizers / huggingface_hub | 5.19.0 / 0.23.2 / 1.33.0 | https://github.com/huggingface/transformers |
| Anthropic Python SDK | 1.12.1 | https://github.com/anthropics/anthropic-sdk-python |
| CLIP ViT-L/14 model (downloaded on first use) | openai/clip-vit-large-patch14 | https://huggingface.co/openai/clip-vit-large-patch14 |
| GeoNames places (CC BY 4.0) | cities5000, countryInfo | https://www.geonames.org/ |
| Natural Earth land polygons (public domain) | 1:50m | https://www.naturalearthdata.com/ |

PhoneInfoga is a separate, unmodified program in `bin/`; it was part of the original project. The other tools are also used without changes to their source code. What changed are the SpyBrain adapters, reports and interface. The full list of Python dependencies and versions is in `requirements-lock.txt`; the build steps are in README and `build.ps1`.

The Qt libraries are dynamic DLLs in `_internal/PySide6`. Individual dependencies may carry their own notices, included in the licenses folder. Map and place data sources and their licenses are listed in `licenses/geodata/README.txt`.

## Online services (not bundled)

SpyBrain calls these services only when you use the matching feature, with your own key where one is needed. Their terms apply to you, not to this project.

| Service | Used for | Terms to know |
|---|---|---|
| Have I Been Pwned (breach search, optional key) | Leaks: breaches that expose an email | Breach data is CC BY 4.0: credit HIBP as the source with a link. Reports do this. https://haveibeenpwned.com/API/v3 |
| Pwned Passwords (no key) | Leaks: is a password known | Only a 5-character SHA-1 prefix is sent (k-anonymity). No attribution required. |
| XposedOrNot (no key) | Leaks: breaches that expose an email | The free API is for personal, low-volume use (25 requests an hour, 100 a day per IP). Products need their paid plan. https://xposedornot.com |
| Google Gemini API | Photo location | Free-tier keys let Google use requests to improve its products. https://ai.google.dev/gemini-api/terms |
| Google Cloud Vision API | Landmarks, web matches | First 1,000 requests per feature each month are free. Needs a standard Cloud API key and billing. |
| Anthropic API | Photo location (Claude) | Billed to your Anthropic account. |
| FaceCheck.ID | Face search | Biometric data; costs credits. Never run on children or teenagers. |
