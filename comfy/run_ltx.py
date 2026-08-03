#!/usr/bin/env python3
"""
Drive the blockout -> photoreal pass through ComfyUI's HTTP API.

You do not have to wire any nodes by hand. This script builds the whole graph,
submits it, waits, and drops the finished mp4 next to your blockout.

Basic use, with ComfyUI running on the same machine:

    python run_ltx.py blockout.mp4 --frames 361 --sigma 0.962

Everything else has a sensible default. The one thing you may need to set is
where ComfyUI keeps its input folder:

    COMFY_INPUT=/path/to/ComfyUI/input   (or --comfy-input)

Requirements inside ComfyUI:
  * the four model files listed in the README, in the right folders
  * the ComfyUI-VideoHelperSuite custom node (provides VHS_LoadVideoPath)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

CKPT        = "ltx-2.3-22b-dev-fp8.safetensors"
TEXT_ENC    = "gemma_3_12B_it_fp4_mixed.safetensors"
LORA_FAST   = "ltx-2.3-22b-distilled-lora-384.safetensors"
LORA_3DREAL = "3DREAL-strong-v2.safetensors"

# A good starting prompt for a vehicle shot. Describe MATERIALS and LIGHT, not
# the object: the model already knows what a car is. See the README.
POS_DEFAULT = (
    "Photorealistic cinematic car chase footage, low chase camera following an orange "
    "mid-engine supercar at speed through a downtown city street. Glossy automotive paint "
    "with sharp reflections of the buildings sliding across the bodywork, carbon fibre "
    "splitter and side skirts, huge alloy wheels with glowing hot brake discs, motion blur "
    "on the spinning wheels. Wet asphalt streaked with reflections, lane markings, kerbs, "
    "traffic, glass and concrete towers rising on both sides, street lights and signage. "
    "The car leans on its suspension, tyres smoking as it slides through the corner. "
    "Overcast afternoon light, shallow depth of field, natural film grain, shot on ARRI "
    "Alexa, anamorphic lens."
)

# Name the thing it might wrongly become. This is the highest-value line in the
# whole file: if your subject keeps coming back as the wrong object, add that
# object here and it usually stops immediately.
NEG_DEFAULT = (
    "toy car, diecast model, miniature, scale model, plastic toy, showroom, parked, static, "
    "studio backdrop, cartoon, anime, cgi, video game, low poly, flat shading, untextured, "
    "clay render, blender viewport, grey blockout, matte painting, illustration, ugly, "
    "blurry, warped geometry, melting, flickering, duplicated wheels, floating car, text, "
    "watermark"
)


def build_graph(video_path, n_frames, sigmas, seed, prefix, fps, pos, neg,
                fast_strength, real_strength):
    """ComfyUI API-format graph. Node ids are strings; a link is [id, slot]."""
    return {
        "1":  {"class_type": "CheckpointLoaderSimple",
               "inputs": {"ckpt_name": CKPT}},
        "2":  {"class_type": "LTXAVTextEncoderLoader",
               "inputs": {"text_encoder": TEXT_ENC, "ckpt_name": CKPT,
                          "device": "default"}},
        # the two LoRAs stack on the base model, in this order
        "3":  {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["1", 0], "lora_name": LORA_FAST,
                          "strength_model": fast_strength}},
        "4":  {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["3", 0], "lora_name": LORA_3DREAL,
                          "strength_model": real_strength}},
        "5":  {"class_type": "CLIPTextEncode",
               "inputs": {"clip": ["2", 0], "text": pos}},
        "6":  {"class_type": "CLIPTextEncode",
               "inputs": {"clip": ["2", 0], "text": neg}},
        "7":  {"class_type": "LTXVConditioning",
               "inputs": {"positive": ["5", 0], "negative": ["6", 0],
                          "frame_rate": float(fps)}},

        # ---- your blockout goes in here, and becomes the STARTING POINT
        "10": {"class_type": "VHS_LoadVideoPath",
               "inputs": {"video": video_path, "force_rate": 0,
                          "custom_width": 0, "custom_height": 0,
                          "frame_load_cap": n_frames, "skip_first_frames": 0,
                          "select_every_nth": 1, "format": "None"}},
        "11": {"class_type": "VAEEncode",
               "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},

        # ---- LTX-2.3 is an audio+video model, so the latent needs both halves
        #      present even though we never use the sound
        "12": {"class_type": "LTXVAudioVAELoader",
               "inputs": {"ckpt_name": CKPT}},
        "13": {"class_type": "LTXVEmptyLatentAudio",
               "inputs": {"frames_number": n_frames, "frame_rate": fps,
                          "batch_size": 1, "audio_vae": ["12", 0]}},
        "14": {"class_type": "LTXVConcatAVLatent",
               "inputs": {"video_latent": ["11", 0], "audio_latent": ["13", 0]}},

        # ---- sampling. cfg 1.0 because the distilled LoRA is already guided;
        #      raising it does nothing useful and costs a lot of time.
        "20": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "21": {"class_type": "CFGGuider",
               "inputs": {"model": ["4", 0], "positive": ["7", 0],
                          "negative": ["7", 1], "cfg": 1.0}},
        "22": {"class_type": "KSamplerSelect",
               "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}},
        "23": {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}},
        "24": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["20", 0], "guider": ["21", 0],
                          "sampler": ["22", 0], "sigmas": ["23", 0],
                          "latent_image": ["14", 0]}},
        "25": {"class_type": "LTXVSeparateAVLatent",
               "inputs": {"av_latent": ["24", 0]}},

        # ---- decode in tiles so a long clip fits in memory
        "30": {"class_type": "LTXVTiledVAEDecode",
               "inputs": {"vae": ["1", 2], "latents": ["25", 0],
                          "horizontal_tiles": 2, "vertical_tiles": 2,
                          "overlap": 6, "last_frame_fix": False,
                          "working_device": "auto", "working_dtype": "auto"}},
        "31": {"class_type": "CreateVideo",
               "inputs": {"images": ["30", 0], "fps": float(fps)}},
        "32": {"class_type": "SaveVideo",
               "inputs": {"video": ["31", 0], "filename_prefix": prefix,
                          "format": "auto", "codec": "auto"}},
    }


def post(host, path, payload):
    req = urllib.request.Request(
        host + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def get(host, path):
    return json.loads(urllib.request.urlopen(host + path, timeout=120).read())


def make_sigma_list(first):
    """A schedule is just a descending list ending at zero. Only the first
    number really matters; the rest step down from it."""
    return f"{first:.4f},{first*0.92:.4f},{first*0.72:.4f},{first*0.42:.4f},0.0"


def main():
    ap = argparse.ArgumentParser(description="Blockout -> photoreal via LTX-2.3 + 3DREAL")
    ap.add_argument("video", help="the blockout mp4 to transform")
    ap.add_argument("--frames", type=int, default=361,
                    help="must be a multiple of 8 plus 1 (default 361)")
    ap.add_argument("--sigma", type=float, default=0.962,
                    help="0.90 keeps your shapes, 0.98 rewrites them (default 0.962)")
    ap.add_argument("--sigmas", default=None,
                    help="full comma-separated schedule, overrides --sigma")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--tag", default="render2real")
    ap.add_argument("--pos", default=os.environ.get("LTX_POS", POS_DEFAULT))
    ap.add_argument("--neg", default=os.environ.get("LTX_NEG", NEG_DEFAULT))
    ap.add_argument("--fast-strength", type=float, default=0.5)
    ap.add_argument("--real-strength", type=float, default=1.0)
    ap.add_argument("--host", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"),
                    help="ComfyUI address (default http://127.0.0.1:8188)")
    ap.add_argument("--comfy-input", default=os.environ.get("COMFY_INPUT"),
                    help="path to ComfyUI/input, where the blockout gets copied")
    ap.add_argument("--ssh", default=os.environ.get("COMFY_SSH"),
                    help="only if ComfyUI runs on another machine, e.g. user@host")
    args = ap.parse_args()

    if (args.frames - 1) % 8 != 0:
        print(f"warning: {args.frames} is not 8n+1. Try 121, 241, 361 or 481.")

    video = os.path.abspath(args.video)
    if not os.path.exists(video):
        sys.exit(f"no such file: {video}")
    name = os.path.basename(video)
    outdir = os.path.dirname(video)

    # ---- 1. put the blockout where ComfyUI can see it
    if args.ssh:
        remote_in = os.environ.get("COMFY_REMOTE_INPUT")
        if not remote_in:
            sys.exit("with --ssh you must also set COMFY_REMOTE_INPUT")
        print(f"[1/4] copying {name} to {args.ssh}")
        r = subprocess.run(["scp", "-q", video, f"{args.ssh}:{remote_in}/{name}"])
        if r.returncode != 0:
            sys.exit("scp failed")
        graph_path = f"{remote_in}/{name}"
    else:
        if not args.comfy_input:
            sys.exit("set --comfy-input (or COMFY_INPUT) to your ComfyUI/input folder")
        dest = os.path.join(args.comfy_input, name)
        if os.path.abspath(dest) != video:
            print(f"[1/4] copying {name} into ComfyUI/input")
            shutil.copy2(video, dest)
        graph_path = dest.replace("\\", "/")

    sigmas = args.sigmas or make_sigma_list(args.sigma)
    graph = build_graph(graph_path, args.frames, sigmas, args.seed, args.tag,
                        args.fps, args.pos, args.neg,
                        args.fast_strength, args.real_strength)

    # ---- 2. submit
    print(f"[2/4] submitting: {args.frames} frames, sigmas {sigmas}")
    try:
        res = post(args.host, "/prompt", {"prompt": graph})
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach ComfyUI at {args.host}. Is it running?  ({e})")
    if "prompt_id" not in res:
        sys.exit("ComfyUI rejected the graph:\n" + json.dumps(res, indent=2)[:3000])
    pid = res["prompt_id"]

    # ---- 3. wait
    print("[3/4] rendering (about 2 minutes on a 5090)")
    t0 = time.time()
    while True:
        time.sleep(5)
        hist = get(args.host, f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            st = entry.get("status", {})
            if st.get("status_str") == "error":
                for m in st.get("messages", []):
                    if m[0] in ("execution_error", "execution_interrupted"):
                        sys.exit("ComfyUI error:\n" + json.dumps(m[1], indent=2)[:2500])
                sys.exit("ComfyUI reported an error")
            files = []
            for _nid, out in entry.get("outputs", {}).items():
                for k in ("images", "video", "videos", "gifs"):
                    for f in (out.get(k) or []):
                        if isinstance(f, dict) and f.get("filename"):
                            files.append(f)
            if files:
                print(f"      done in {time.time() - t0:.0f}s")
                break
            sys.exit("finished but produced no video")
        if time.time() - t0 > 3000:
            sys.exit("timed out")
        print(f"      ...{time.time() - t0:.0f}s", flush=True)

    # ---- 4. collect
    for f in files:
        sub = f.get("subfolder", "")
        rel = (sub + "/" if sub else "") + f["filename"]
        local = os.path.join(outdir, f["filename"])
        if args.ssh:
            remote_out = os.environ.get("COMFY_REMOTE_OUTPUT")
            if not remote_out:
                print(f"[4/4] left on the remote machine: {rel}")
                continue
            subprocess.run(["scp", "-q", f"{args.ssh}:{remote_out}/{rel}", local])
        else:
            src = os.path.join(os.path.dirname(args.comfy_input), "output", rel)
            if os.path.exists(src):
                shutil.copy2(src, local)
            else:
                print(f"[4/4] saved by ComfyUI as: {rel}")
                continue
        print(f"[4/4] -> {local}")


if __name__ == "__main__":
    main()
