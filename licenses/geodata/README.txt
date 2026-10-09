Data used by the Locate page

Places (assets/geo/places.tsv.gz, countries.json)
  GeoNames, cities with a population of 5,000 or more, and country names.
  Source: https://download.geonames.org/export/dump/ (cities5000.zip, countryInfo.txt)
  License: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
  Changes: reduced to name, country code, coordinates and population; compressed.

World map (assets/geo/land.json.gz)
  Natural Earth, 1:50m land polygons. Public domain.
  Source: https://www.naturalearthdata.com/ (via github.com/nvkelso/natural-earth-vector)
  Changes: outer rings only, coordinates rounded to 0.05 degrees.

CLIP ViT-L/14 model (downloaded on first use of GeoCLIP, not bundled)
  OpenAI, openai/clip-vit-large-patch14 on Hugging Face. MIT License.
  Stored in %LOCALAPPDATA%\OSINT Hub\models.
