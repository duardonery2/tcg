# Stability AI — Stable Image Ultra API

Reference notes for the `POST /v2beta/stable-image/generate/ultra` endpoint (Stability AI Platform API), for use in this project as a possible replacement/alternative to the DALL·E 3 call in `main.py`.

> ⚠️ **Key handling**: never hardcode the API key in source files or commit it to git. Load it from an environment variable (e.g. `STABILITY_API_KEY`) or a `.env` file that's gitignored. If a key was ever pasted into a chat, terminal history, or committed by mistake, treat it as leaked and rotate it from the [Stability AI dashboard](https://platform.stability.ai/account/keys).

## Overview

- **Model**: Stable Image Ultra — Stability's highest-fidelity text-to-image (and image-to-image) model, built on Stable Diffusion 3.5 with additional prompt-adherence tuning.
- **Endpoint**: `https://api.stability.ai/v2beta/stable-image/generate/ultra`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`
- **Cost**: 8 credits per successful generation (failed/moderated generations are not billed).

## Authentication

```
Authorization: Bearer <STABILITY_API_KEY>
```

Pass the key as a Bearer token. There is no separate `organization` header required for this endpoint.

## Request headers

| Header | Required | Value | Purpose |
|---|---|---|---|
| `Authorization` | Yes | `Bearer sk-...` | API key |
| `Accept` | No | `image/*` (default) or `application/json` | `image/*` returns raw image bytes; `application/json` returns a base64-encoded image plus metadata |
| `Content-Type` | Yes | `multipart/form-data` | Set automatically by most HTTP clients when sending form fields |

## Request body (multipart form fields)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | **Yes** | — | 1–10,000 characters. What you want to see in the image. |
| `negative_prompt` | string | No | — | 1–10,000 characters. What you do NOT want to see. Not usable in combination with a `style_preset` that overrides it heavily; generally applied as-is. |
| `aspect_ratio` | string (enum) | No | `1:1` | One of: `16:9`, `1:1`, `21:9`, `2:3`, `3:2`, `4:5`, `5:4`, `9:16`, `9:21`. Ignored if `image` is provided in image-to-image mode (output matches the input image's aspect ratio). |
| `seed` | integer | No | `0` | `0`–`4294967294`. `0` means a random seed is used. Returned in the response for reproducibility. |
| `output_format` | string (enum) | No | `png` | One of: `png`, `jpeg`, `webp`. |
| `style_preset` | string (enum) | No | — | One of: `3d-model`, `analog-film`, `anime`, `cinematic`, `comic-book`, `digital-art`, `enhance`, `fantasy-art`, `isometric`, `line-art`, `low-poly`, `modeling-compound`, `neon-punk`, `origami`, `photographic`, `pixel-art`, `tile-texture`. |
| `mode` | string (enum) | No | `text-to-image` | `text-to-image` or `image-to-image`. |
| `image` | binary file | Only if `mode=image-to-image` | — | Input image for image-to-image mode. Supported formats: jpeg, png, webp. Each side must be at least 64px; total pixel count between 4,096 and ~9,437,184px (dimensions divisible by 64 recommended). |
| `strength` | number | Only if `mode=image-to-image` | — | `0`–`1`. How much the input `image` influences the result: `0` = ignore input image, `1` = ignore the prompt almost entirely. |

## Example request (curl)

```bash
curl -f -sS https://api.stability.ai/v2beta/stable-image/generate/ultra \
  -H "Authorization: Bearer $STABILITY_API_KEY" \
  -H "Accept: image/*" \
  -F prompt="A masterpiece fantasy trading card illustration of a fire knight, dark fantasy, highly detailed, digital painting, dramatic lighting, no text, centered composition" \
  -F aspect_ratio="1:1" \
  -F output_format="png" \
  -o card_art.png
```

To get JSON with base64 + metadata instead of raw bytes, swap the `Accept` header:

```bash
curl -f -sS https://api.stability.ai/v2beta/stable-image/generate/ultra \
  -H "Authorization: Bearer $STABILITY_API_KEY" \
  -H "Accept: application/json" \
  -F prompt="A masterpiece fantasy trading card illustration of a fire knight" \
  -F output_format="png"
```

## Example request (Python, matching this project's `requests`-based style)

```python
import os
import requests

STABILITY_API_KEY = os.environ["STABILITY_API_KEY"]  # never hardcode the key

def gerar_arte_ia_stability(nome, tipo, elemento):
    """Gera a imagem usando Stability AI (Stable Image Ultra)."""
    prompt = (
        f"A masterpiece fantasy trading card game illustration of {nome}. "
        f"Concept: {tipo} of the {elemento} element. "
        "Style: Dark fantasy, highly detailed, digital painting, dramatic lighting, "
        "no text, centered composition."
    )

    response = requests.post(
        "https://api.stability.ai/v2beta/stable-image/generate/ultra",
        headers={
            "Authorization": f"Bearer {STABILITY_API_KEY}",
            "Accept": "image/*",
        },
        files={"none": ""},  # required by `requests` to force multipart encoding
        data={
            "prompt": prompt,
            "aspect_ratio": "1:1",
            "output_format": "png",
        },
    )

    if response.status_code != 200:
        raise Exception(f"Stability API error {response.status_code}: {response.text}")

    return response.content  # raw PNG bytes; wrap in BytesIO + Image.open as needed
```

## Response

### Success — `200 OK`

- If `Accept: image/*`: body is the raw image (content-type matches `output_format`, e.g. `image/png`).
  - Response header `finish-reason` — `SUCCESS`, or `CONTENT_FILTERED` if the output was flagged and returned blurred.
  - Response header `seed` — the seed actually used.
- If `Accept: application/json`: JSON body:

```json
{
  "image": "<base64-encoded image data>",
  "finish_reason": "SUCCESS",
  "seed": 343940597
}
```

`finish_reason` values: `SUCCESS`, `CONTENT_FILTERED`.

### Errors

| Status | Meaning |
|---|---|
| `400` | Invalid request parameters (e.g. bad enum value, malformed multipart body). |
| `403` | Request flagged by content moderation before generation. |
| `413` | Request body / input image too large. |
| `422` | Validation error (e.g. missing required field, out-of-range value). |
| `429` | Rate limited — too many requests. |
| `500` | Unexpected server error. |

Error body shape:

```json
{
  "id": "<request-id>",
  "name": "<error-name>",
  "errors": ["human-readable message"]
}
```

## Practical notes for this project

- This project currently generates card art with DALL·E 3 in `main.py` (`gerar_arte_ia`). Stable Image Ultra is a drop-in alternative: swap the OpenAI call for the `requests.post` call above and adapt `montar_carta` to open the returned bytes with `PIL.Image.open(BytesIO(...))`, same as it already does for the OpenAI image URL.
- Aspect ratio `1:1` at output size ~1MP fits the current `resize((600, 600))` step in `montar_carta` without heavy upscaling artifacts.
- Consider `style_preset="fantasy-art"` or `"digital-art"` to match the "dark fantasy, digital painting" look already used in the prompt.

## Source

- [Stability AI API Reference — Generate Ultra](https://platform.stability.ai/docs/api-reference#tag/Generate/paths/~1v2beta~1stable-image~1generate~1ultra/post)
