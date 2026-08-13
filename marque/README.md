# Marque PrevuFlow

## Le symbole

Une courbe de solde qui creuse, touche son point bas, puis remonte
au-dessus de son point de départ. Le disque ambre marque le creux —
c'est l'information que l'utilisateur vient chercher, et la seule tache
de couleur du logo.

La remontée est plus haute que le départ : c'est délibéré. Une parabole
symétrique se lit comme un sourire ; celle-ci se lit comme un graphe.

## Les couleurs

| Rôle | Code | Usage |
|---|---|---|
| Marine | `#123e53` | fond du symbole, mot « Prevu » |
| Ambre | `#df8d20` | le point bas, et rien d'autre |
| Vert | `#1F7244` | mot « Flow », actions dans l'application |
| Blanc | `#ffffff` | la courbe |

Ce sont exactement celles de `theme.py`. Le logo ne crée pas une palette
de plus.

## Les fichiers

| Fichier | Pour quoi |
|---|---|
| `logo.svg` | la source. Tout le reste en découle |
| `logo-mono.svg` | un seul ton : gravure, tampon, télécopie, impression en noir |
| `logo-horizontal.svg` | symbole et nom côte à côte : en-tête, signature, facture |
| `logo-1024.png` | image de partage, réseaux, place de marché |
| `logo-horizontal-900.png` · `-1800.png` | documents, présentations |
| `apercu.png` | le contrôle à 16, 32 et 64 pixels |

Les icônes de l'application vivent dans `static/` et sont produites à
partir de `logo.svg` :
`favicon.png` (64), `apple-touch-icon.png` (180), `icon-192.png`,
`icon-512.png`.

## Refabriquer les icônes

Après toute modification de `logo.svg` :

```bash
pip install cairosvg
python - <<'PY'
import cairosvg, pathlib
src = pathlib.Path("marque/logo.svg").read_bytes()
for chemin, taille in (("static/favicon.png", 64),
                       ("static/apple-touch-icon.png", 180),
                       ("static/icon-192.png", 192),
                       ("static/icon-512.png", 512),
                       ("marque/logo-1024.png", 1024)):
    cairosvg.svg2png(bytestring=src, write_to=chemin,
                     output_width=taille, output_height=taille)
PY
```

## Ce qu'on ne fait pas

- Pas de dégradé, pas d'ombre portée : le symbole doit rester imprimable
  en une couleur.
- L'ambre ne sert qu'au point bas. S'en servir ailleurs lui ferait perdre
  son sens.
- Pas d'étirement : le symbole est carré, le format horizontal a son
  propre fichier.
