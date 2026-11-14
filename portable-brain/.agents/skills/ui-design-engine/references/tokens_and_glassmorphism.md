# Liquid Glass Design Tokens & Micro-Skeuomorphic Physics

> **Universal CSS Variables & Depth Tokens for Dark Glassmorphism**

---

## 1. Liquid Glass Panel Token

```css
.liquid-glass-panel {
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 
    inset 0 1px 0 0 rgba(255, 255, 255, 0.12),  /* Specular top lip */
    inset 0 -1px 0 0 rgba(0, 0, 0, 0.4),         /* Recessed bottom lip */
    0 12px 32px -4px rgba(0, 0, 0, 0.5),         /* Directional depth */
    0 4px 12px -2px rgba(0, 0, 0, 0.3);
}
```

---

## 2. Liquid Glass Interactive Button Token

```css
.liquid-glass-button {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.02) 100%), rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 
    inset 0 1px 0 rgba(255, 255, 255, 0.2),
    0 2px 4px rgba(0, 0, 0, 0.25);
  transition: all 150ms cubic-bezier(0.16, 1, 0.3, 1);
}

.liquid-glass-button:hover {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.04) 100%), rgba(51, 65, 85, 0.8);
  border-color: rgba(255, 255, 255, 0.2);
}

.liquid-glass-button:active {
  transform: translateY(0.5px);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.4);
}
```

---

## 3. Tactile & Skeuomorphic Micro-Accents

1. **Machined Chamfers**: 45-degree corner bevels via `clip-path: polygon()` or SVG borders for hardware/tech consoles.
2. **Milled Switch Insets**: Micro-recesses using inner shadows (`box-shadow: inset 0 2px 4px rgba(0,0,0,0.6)`).
3. **LED Status Indicators**: Physical optic jewels: a crisp 6px solid dot with a 1px ring and a tight 3px glow (never an oversized pulsing neon orb).
4. **Physical Tactile Depression**: Immediate interactive feedback on `:active` with `translate-y-[0.5px]` and specular highlight dimming.

---

## 4. Mobile Touch Expansion Utility

Ensure touch targets always evaluate to $\ge 44\text{px}$ without visually warping small icons:

```css
.touch-target-expand {
  position: relative;
}
.touch-target-expand::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  min-width: 44px;
  min-height: 44px;
  width: 100%;
  height: 100%;
}
```
