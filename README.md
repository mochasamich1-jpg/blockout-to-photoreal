# From Boxes to Photoreal

Build a shot out of plain coloured blocks in Blender. Let an AI repaint every frame
into something photographic, keeping your exact camera move, timing and motion.

You do not need to model, texture, light or render well. You need the right
**shape** and the right **movement**. Everything else comes free.

**[Read the full illustrated guide →](https://mochasamich.com/guide.html)**
<sub>(mirror: [GitHub Pages](https://mochasamich1-jpg.github.io/blockout-to-photoreal/))</sub>

---

## What you get

| | |
|---|---|
| **Input** | 361 flat-shaded frames of orange boxes on a grey road |
| **Output** | A 15 second photoreal supercar chase, 1080x1920 |
| **Render time** | About 2 minutes on an RTX 5090 |

The repo has two worked examples. The **car** (`blender/`) is the tutorial and it
works on the first try. The **mech** (`examples/mech/`) is the same pipeline on a
much harder subject, included because the honest comparison is the most useful
lesson here. See [Pick your subject carefully](#pick-your-subject-carefully).

---

## Downloads

GitHub cannot host multi-gigabyte model weights, so these are direct links. Click
and save each file into the folder shown. **Total download is about 43 GB**, so
start it before you do anything else.

### Models (required)

| File | Goes in | Size | Download |
|---|---|---|---|
| `ltx-2.3-22b-dev-fp8.safetensors` | `ComfyUI/models/checkpoints/` | 27.1 GB | [Lightricks/LTX-2.3-fp8](https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors) |
| `gemma_3_12B_it_fp4_mixed.safetensors` | `ComfyUI/models/text_encoders/` | 8.8 GB | [Comfy-Org/ltx-2](https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors) |
| `ltx-2.3-22b-distilled-lora-384.safetensors` | `ComfyUI/models/loras/` | 7.1 GB | [Lightricks/LTX-2.3](https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors) |
| `3DREAL-strong-v2.safetensors` | `ComfyUI/models/loras/` | 320 MB | [fal/LTX-2.3-3DREAL-LoRA](https://huggingface.co/fal/LTX-2.3-3DREAL-LoRA/resolve/main/3DREAL-strong-v2.safetensors) |

What each one does: the checkpoint is the video model. The distilled LoRA makes it
run in four steps instead of thirty. **3DREAL is the magic one**, trained
specifically to turn 3D renders into photographs. Gemma reads your prompt.

> **Download tip.** Hugging Face rejects multi-connection downloaders. If a download
> manager keeps dying at 403, use a plain single-stream `curl -L -o <file> <url>`
> instead.

Optional upgrades, same folders:

- [`ltx-2.3-22b-distilled-lora-384-1.1.safetensors`](https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384-1.1.safetensors) is a newer distilled LoRA with better fast-motion stability. Worth trying for chase shots.
- [`3DREAL-light.safetensors`](https://huggingface.co/fal/LTX-2.3-3DREAL-LoRA/resolve/main/3DREAL-light.safetensors) transforms less and preserves your blockout more.

### Tools (all free)

| Tool | What for | Link |
|---|---|---|
| Blender | Building the blockout | [blender.org/download](https://www.blender.org/download/) |
| ComfyUI | Running the AI model | [github.com/comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) |
| ComfyUI-VideoHelperSuite | Required custom node, loads your video | [github.com/Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) |
| ffmpeg | Frames to video, and the final polish | [ffmpeg.org/download](https://ffmpeg.org/download.html) |

---

## Can your computer run this?

This is the honest gate. Check it before spending an evening on the rest.

| Your GPU | Verdict |
|---|---|
| NVIDIA, 32 GB (RTX 5090) | Comfortable. Full 361 frame clips. |
| NVIDIA, 24 GB (3090, 4090) | Works. Use shorter clips, 121 or 241 frames. |
| NVIDIA, 16 GB | Tight. Expect to fight it. |
| Under 16 GB, or AMD / Intel / laptop | Not going to work locally. |

**If your card is too small, do not give up on the idea.** Stage one is the
valuable half and it runs on any computer. Build the blockout in Blender, export
the video, then push it through a hosted video-to-video service instead of running
the model locally. You lose fine control over the sigma dial, but the core trick
still works.

---

## Quick start

```bash
git clone https://github.com/mochasamich1-jpg/blockout-to-photoreal
cd blockout-to-photoreal

# 1. render the blockout (about 7 minutes, mostly scene building)
blender -b -P blender/build_race.py -- ./frames

# 2. frames into a video. High quality: this is the AI's only input.
ffmpeg -y -framerate 24 -i frames/bl_%04d.png \
  -c:v libx264 -crf 12 -pix_fmt yuv420p blockout.mp4

# 3. the AI pass. Start ComfyUI first.
python comfy/run_ltx.py blockout.mp4 --sigma 0.962 \
  --comfy-input /path/to/ComfyUI/input

# 4. upscale for delivery
ffmpeg -y -i render2real_00001_.mp4 \
  -vf "scale=1080:1920:flags=lanczos,unsharp=5:5:0.30:5:5:0.0" \
  -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p final.mp4
```

`run_ltx.py` builds the entire ComfyUI graph for you. You never have to wire a node.

To check your subject on its own before building a whole scene:

```bash
blender -b -P blender/car_probe.py -- ./probe
```

---

## The five blockout rules

Every one of these was learned by getting it wrong.

1. **Silhouette beats detail.** The outline is what the AI reads. On the car, what
   mattered was huge wheels against a very low body, not door handles.

2. **Give every part a different, saturated colour.** Not optional. A grey blockout
   barely transforms at all. The colour separation is how the AI works out which
   part is which.

3. **Keep the lighting flat and mid-tone.** Use Blender's **Workbench** engine, not
   Cycles or Eevee. Overcast daylight. Night scenes collapse into mush.

4. **Do not model smoke, fire or dust.** The AI invents these far better than you
   can, and a modelled smoke cloud comes back as a solid grey slab.

5. **Never let the subject touch the edge of frame.** The moment part of it is
   cropped, the AI invents a replacement, and it invents something wrong.
   `build_race.py` includes an automatic check for this.

And one about motion: **move the body, not the whole car.** The wheels stay planted
on the road while the body rolls into corners, dives under braking and squats under
power. A vehicle moved as one rigid lump reads as a sticker sliding on glass.

---

## The one dial that matters

Sigma controls how much freedom the AI gets.

| Sigma | Result |
|---|---|
| 0.90 | Keeps your shapes perfectly. World stays flat and CG. |
| **0.962** | Wet reflective asphalt, real paint, motion intact. Used for the car. |
| 0.98 | Gorgeous, and it quietly rewrites your scene. |

At 0.975 the car looked better in every straight-line frame **and had silently
deleted the drift**, pointing the car straight down the road instead. So:

> **Tune sigma against the hardest frame in your shot, not a pretty one.**

Weak-prior subjects want lower. The mech example needed 0.935.

---

## When it goes wrong

| What you see | What to do |
|---|---|
| Looks like a video game | Raise sigma. |
| Your subject turned into something else | Lower sigma. Name the wrong thing in the negative prompt. Check nothing is cropped. |
| A special pose vanished | Sigma too high. Come down in small steps. |
| Everything is grey mush | Your blockout is too grey. Give parts strong separate colours. |
| Proportions look wrong | Fix it in Blender. No prompt fixes a bad silhouette. |
| Legs or wheels look spindly | Build them chunkier. Mass is preserved literally. |
| Modelled smoke is a grey slab | Delete it and describe it in the prompt instead. |

The single most useful trick: **name the wrong thing in the negative prompt.** The
mech's shoulder pods kept coming back as stacked wooden ammo crates. Adding
`wooden crate, plywood, packing case` to the negative fixed it immediately.

---

## Pick your subject carefully

This matters more than any setting on this page.

Same pipeline, same machine, same day: the **car was photoreal on the first
attempt**. The **mech took six rounds and still only half worked.**

The reason is simple. There is an enormous amount of real footage of cars, streets,
buildings, weather and animals. There is none of a giant walking war machine, so
when the AI is unsure it substitutes the nearest real thing it knows, and you get a
crane, or a tracked vehicle, or wooden crates where the missile pods should be.

- **Easy mode:** cars, motorbikes, boats, planes, trains, animals, storms, cities.
- **Hard mode:** invented machines and creatures.

Both are possible. Just know which you picked before you start, because it decides
how many evenings this takes.

---

## Repo layout

```
blender/
  car_rig.py        the supercar, fully parametric
  build_race.py     city, traffic, driving physics, camera, framing check
  car_probe.py      renders the car alone from six angles
comfy/
  run_ltx.py        builds and runs the whole ComfyUI graph
examples/mech/      the same pipeline on a hard subject
docs/               the illustrated guide
```

## Credits

Built on [LTX-2.3](https://huggingface.co/Lightricks/LTX-2.3) by Lightricks and the
[3DREAL LoRA](https://huggingface.co/fal/LTX-2.3-3DREAL-LoRA) by fal, running in
[ComfyUI](https://github.com/comfyanonymous/ComfyUI). Every number in this repo came
from a shot that actually rendered, not a spec sheet.

MIT licensed. Do what you like with it.
