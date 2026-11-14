# Batch Asset Manifest Templates for Asset Studio Pro (Google Flow)

> **Role Specification**:
> *"You are the Lead Technical Director and Pipeline Architect for 'Asset Studio Pro'. Your job is to generate production-ready visual asset manifests for batch image and video generation."*

---

## 1. Syntax & Header Directives
Every asset block begins with an `===` header line and ends with `---`:
```text
=== ID: [unique_id] | TYPE: [image|video] | CHAR: [CharacterName] | ASPECT: [ratio] | FOLDER: [path] | MODEL: [model_name] | STYLE: [prefix] | NEGATIVE: [neg] | MUTED: [true|false] ===
[Detailed Prompt on the following lines]
---
```

- **Models**:
  - Image: `🍌 Nano Banana Pro` (default), `🍌 Nano Banana 2.1`, `🍌 Nano Banana 2 Lite`
  - Video: `Omni 1.1 Flash` (default), `Veo 3.1 - Quality`, `Veo 3.1 - Fast`, `Veo 3.1 - Lite`
- **Aspect**: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`
- **Output Format**: No ZIP files. Direct filesystem export with double underscore encoding (`[folder]__[subfolder]__[filename].[ext]`) and `package_manifest.json`.

---

## 2. Character & Cinematic Combo (Character Forge)

```text
=== ID: hero_portrait_01 | TYPE: image | CHAR: Neon Voyager | ASPECT: 3:4 | FOLDER: characters/neon_voyager/portraits | MODEL: 🍌 Nano Banana Pro ===
Heroic 3/4 angle portrait of the character standing atop a rain-slicked skyscraper, rim lighting in neon magenta and cyan, hyper-detailed cyberpunk jacket fabric, atmospheric haze and bokeh.
---
=== ID: hero_cinematic_01 | TYPE: video | CHAR: Neon Voyager | ASPECT: 16:9 | FOLDER: characters/neon_voyager/cinematics | MODEL: Omni 1.1 Flash | MUTED: false ===
Cinematic dolly forward shot as the character turns slowly to face the camera, wind fluttering clothes, distant holographic billboards flickering in the rainy metropolis.
---
```

---

## 3. Environment & Matte Painting (World Building)

```text
=== ID: obsidian_citadel_wide | TYPE: image | ASPECT: 16:9 | FOLDER: environments/citadel/vistas | MODEL: 🍌 Nano Banana 2.1 | STYLE: Dark fantasy matte painting, cinematic scale, volumetric fog ===
Massive monolithic fortress carved directly into sharp obsidian mountain cliffs, glowing purple arcane conduits pulse along the stone terraces, twin moons hanging in a dark violet twilight sky.
---
=== ID: citadel_flyover_drone | TYPE: video | ASPECT: 16:9 | FOLDER: environments/citadel/flyovers | MODEL: Omni 1.1 Flash ===
Sweeping slow aerial drone flyover gliding past jagged mountain crags revealing the towering citadel entrance, volumetric clouds parting beneath the camera.
---
```

---

## 4. UI Artifacts & Relic Icons

```text
=== ID: relic_celestial_compass | TYPE: image | ASPECT: 1:1 | FOLDER: ui/icons/relics | MODEL: 🍌 Nano Banana Pro | STYLE: High-end RPG item icon, dark studio background, glowing rim light ===
Intricate ancient bronze astrolabe floating in mid-air, spinning concentric rings embedded with glowing sapphire crystals, soft particle sparks drifting outward.
---
=== ID: potion_void_elixir | TYPE: image | ASPECT: 1:1 | FOLDER: ui/icons/potions | MODEL: 🍌 Nano Banana Pro | STYLE: High-end RPG item icon, dark studio background, glowing rim light ===
Ornate crystal vial filled with swirling iridescent purple and gold fluid, stopper sealed with a wax emblem of an eye, delicate glass reflections.
---
```

---

## 5. Technical Pedagogical STEM Visual Plates (Computer Science)

```text
=== ID: TP_01_silicon_die_macro | TYPE: image | ASPECT: 16:9 | FOLDER: dsa_masterclass/hardware_plates | MODEL: 🍌 Nano Banana Pro | STYLE: High-end editorial macro photography, dark obsidian void #0A0B0E, cinematic lighting | NEGATIVE: text, watermark, logo, numbers, letters, labels, blurry, cartoon, low-res ===
Architectural macro photograph of an exposed modern multicore CPU silicon die, etched microscopic ALU logic gates and register blocks glowing with subtle tungsten gold (#D4AF37) and sky cyan (#38BDF8) conduits, receding into a dark obsidian void (#0A0B0E), left 45 percent in clean deep shadow for vector typography, 85mm f/1.8 architectural lens, no text, no numbers, no letters.
---
```
