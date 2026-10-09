# AFTER Studio

A personal creative studio powered by WanGP. Lazy presets for a first image; Custom for model, steps, seed, format and reference images. Independent project, not affiliated with Higgsfield.

## Use on this Mac

From the repository root, after installing the main WanGP requirements into `.venv`:

```sh
./studio/start.sh
```

On macOS, you can also double-click `studio/Start AFTER.command`. Keep its terminal open. Open http://127.0.0.1:7861, describe an image, then choose **Créer**. Lazy defaults to Flux 2 Klein, four steps, 512 × 512. The first run downloads the model. Subsequent generations still reload its weights so that idle workers do not occupy GPU memory.

The original WanGP UI can run separately on port 7860. Avoid simultaneous generation in both interfaces on a 16 GB Mac.

## Hosted interface

Production URL: https://after-studio.vercel.app

Vercel serves only `studio/web`. Python, GPU inference, model weights, job history, references and generated files stay on the Mac. No paid inference API, tunnel, public backend or LAN listener is used.

1. Start the local engine with the command above.
2. Open the hosted interface **on the same Mac** and choose **Connecter mon Mac**.
3. In the local window, verify the exact HTTPS origin and choose **Autoriser**.
4. Allow local-network access if the browser asks. The header must show **Mac connecté** before you can create.

If the popup cannot open, the connection panel offers a manual pairing code. If the browser cannot access loopback, use **Ouvrir directement le studio sur ce Mac**; it has the same features. Pairing approval alone does not prove network connectivity. The Codex integrated browser's cloud-to-loopback requests timed out during this session; that browser path is not yet validated.

Access expires after 30 days and is revocable under the local studio's information button. Tokens are bound to an exact origin, stored as hashes by the engine, and sent in authorization headers, never media URLs. The hosted UI retrieves media as authenticated blobs. The local server accepts only localhost/127.0.0.1 hostnames, protects pairing endpoints from remote use, and rejects unapproved origins.

## Behavior

- One isolated subprocess per generation; progress, persistent history, cancellation and a 30-minute limit.
- Idempotency keys prevent repeated submissions from launching the same accepted request twice.
- Prompt drafts survive reloads in browser storage.
- Uploads are validated, stripped of metadata, converted to PNG and limited to 10 MB / 25 million input pixels.
- Gallery results can be downloaded, reused or removed. Removing a job moves its record into `.studio/trash`; media remains on disk.
- Interrupted jobs become explicit failures after restart. Entirely black outputs are rejected.
- Images and two-second Wan videos are exposed; **video and alternative image models remain experimental and have not been validated here**. Video tooling may require FFmpeg/FFprobe installation on macOS.

All local data is under `.studio/`, ignored by Git. Model downloads use `ckpts/`. Never deploy the repository root or upload local data; the Vercel project root is `studio/web`.

## Verification

```sh
.venv/bin/python -m unittest studio.test_server studio.test_mps -v
node --test studio/test_bridge.cjs
node --check studio/web/assets/studio.js
```

There are 15 API checks, seven JavaScript transport checks, and an isolated macOS regression check for MPS synchronization, idempotent patch installation and BF16 reference normalization. GitHub Actions runs the API and transport checks; the MPS check needs a Mac.

Real local tests on 9 October 2026, M2 Pro / 16 GB:

- Text-to-image: a red ceramic cup and a matte black perfume bottle produced actual images. The bottle completed through the studio UI in about 106 seconds; its browser download matches the generated file.
- Reference editing: the black bottle became green glass after correcting an MPS normalization crash, completing in about 128 seconds. A further run confirmed the selected landscape format (768 × 432) in 144 seconds. Legacy history also reports actual output dimensions.
- The original all-black outputs were traced to unsafe MPS synchronization around reused model buffers. The compatibility patch now synchronizes these fences and only installs once.
- Desktop and 390 px layout (no horizontal overflow), draft persistence, Lazy/Custom, gallery, errors, reuse and download were exercised. This is a tested personal image workflow, not a claim that every upstream model or video pipeline is production-ready.

## Deploy

Link the GitHub fork to Vercel, set Root Directory to `studio/web`, framework to Other, no build/install commands, output directory `.`. `vercel.json` sets content security and cache headers. The current implementation lives on `codex/minimal-studio`; deploy that branch for Studio updates. The fork's `main` remains upstream WanGP.

## Credits

WanGP and its model licenses apply. Inspiration cards are explicitly labeled Unsplash reference photographs, not generated results; sources are in `studio/web/assets/SOURCES.txt`. Icons: Lucide (ISC). Fonts: DM Sans and Space Grotesk through Google Fonts, with system fallbacks.
