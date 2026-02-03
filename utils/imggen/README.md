## Flux2 klein base
```json
{
  "pipeline": "flux2_klein_t2i",
  "params": {
    "prompt": "cinematic portrait of a cyberpunk detective, neon rain, 2000s digicam flash, slight noise, candid street photo",
    "negative": "blurry, lowres, extra fingers, deformed hands, watermark, text",
    "width": 1024,
    "height": 1024,
    "steps": 20,
    "cfg": 5,
    "seed": 123,
    "filename_prefix": "Flux2-Klein-Base"
  }
}

```

## Flux2 klein distilled
```json
{
  "pipeline": "flux2_klein_t2i_distilled",
  "params": {
    "prompt": "portrait photo of a cyberpunk detective, neon rain, film grain",
    "width": 1024,
    "height": 1024,
    "steps": 4,
    "cfg": 1,
    "seed": 123,
    "filename_prefix": "Flux2-Klein-D"
  }
}
```

## Flux2 klein distilled GGUF
```json
{
  "pipeline": "flux2_klein_t2i_distilled_gguf",
  "params": {
    "prompt": "full body shot of a woman in emerald techwear, rainy street, 2000s digicam flash",
    "width": 768,
    "height": 1152,
    "steps": 4,
    "cfg": 1,
    "seed": 42,
    "filename_prefix": "Flux2-Klein-GGUF"
  }
}
```