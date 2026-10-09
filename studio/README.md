# AFTER Studio

A minimal local creative studio powered by **WanGP**, with Lazy presets and a Custom panel. This is an independent interface, not affiliated with Higgsfield.

## Run

From the repository root, after installing the main WanGP requirements:

```sh
.venv/bin/python -m studio.server
```

Open http://127.0.0.1:7861. The original WanGP interface can stay on port 7860; do not run generations simultaneously in both on a memory-constrained machine.

## Features

- Real WanGP Python API generation, isolated in one subprocess per job.
- Images (Flux 2 Klein by default) and experimental two-second Wan 2.1 videos.
- Prompt presets, aspect ratio, quality, image reference upload.
- Custom model, steps, seed, plus a link to the full WanGP interface.
- Persistent job history, progress, cancellation, errors, engine logs, file download and prompt reuse.
- No account, paid API or cloud inference. The first generation downloads model files from upstream sources.

Data lives in `.studio/` (ignored by Git); model downloads use WanGP's normal `ckpts/` directory. The worker releases loaded models after each job to recover memory. Thus each generation pays a model-loading cost. The server binds to loopback, rejects cross-origin writes, and serves generated files only from its own media directory. It is intended for local personal use, not public hosting.

## Verification

```sh
.venv/bin/python -m unittest studio.test_server
```

UI readiness does not imply a particular model works on every GPU. WanGP's Apple Silicon support is experimental, and video export requires FFmpeg. No synthetic output is substituted when the engine fails.

## Credits

Generation engine: WanGP, under its repository license. Model licenses also apply. The UI discloses the WanGP integration. Inspiration cards use photographs from Unsplash (source image URLs in `studio/web/assets/SOURCES.txt`); they are explicitly marked as reference photos, not generated results. Icons: Lucide (ISC). Typography: DM Sans and Space Grotesk, served by Google Fonts (falls back to system fonts offline).

## Local verification — 9 October 2026

The UI was exercised at desktop size and at 390 px: Lazy/Custom, presets, draft persistence, history, failure detail and prompt reuse. Nine API/unit checks pass. Three real Flux 2 Klein jobs on this M2 Pro / 16 GB reached model loading, text encoding, four denoising steps and export, but produced all-black images. Forcing BF16 and using FP32 VAE decoding did not resolve this. These jobs are marked as failures, with engine logs retained; image generation on this machine is **not yet validated**. Video and reference-conditioned inference have not been validated end to end. The studio does not substitute stock imagery for generated output.
