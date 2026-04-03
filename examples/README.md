# Example Files

This directory contains sample files for testing the Decoration Preview Service API.

## Sample Artwork

- **`sample_artwork.png`** — A 512×512 decorative badge pattern (PNG with transparency) that can be used to test the render endpoint.

## Usage

From the project root, start the server and submit a render job:

```bash
# Start the server
uvicorn backend.app.main:app --reload --port 8000

# Submit a render job with the sample artwork
curl -X POST http://localhost:8000/api/v1/render \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -F "artwork_file=@examples/sample_artwork.png" \
  -F "element_id=elem-minifig-torso-001" \
  -F "output_format=png" \
  -F "resolution_width=1024" \
  -F "resolution_height=1024"
```
