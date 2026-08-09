"""
THÈME — apparence commune à tous les écrans
Dayzon — SMD Global Consulting LLC

Ce module ne contient aucune logique métier : il fabrique du HTML et pose
le style. Il est le seul endroit où une couleur est écrite en dur.

Ce qui a été retenu du prototype mobile, et ce qui ne l'a pas été
-----------------------------------------------------------------
Retenu : la palette, les cartes, le solde en tête d'écran, les indicateurs
en grille, les messages d'analyse en encarts colorés, la grille du
calendrier, les opérations en lignes datées.

Écarté, parce que Streamlit ne le permet pas : la barre de navigation
basse, le bouton flottant, les panneaux coulissants, le menu latéral sur
mesure. Streamlit impose sa barre latérale et son flux vertical ; on peut
en changer l'apparence, pas la structure. Les simuler en CSS donnerait des
éléments qui ne réagissent pas au clic — pire qu'une absence.

Une règle tenue partout : aucun texte sous 11 pixels. Le prototype
descendait à 7, illisible sur un téléphone tenu à bout de bras.
"""

from __future__ import annotations

import html as _html

import streamlit as st

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

ENCRE = "#142837"
MARINE = "#123e53"
MARINE_CLAIR = "#194f66"
VERT = "#1F7244"
VERT_CLAIR = "#2e8b59"
MENTHE = "#dff0e7"
MENTHE_PALE = "#eff8f3"
ROUGE = "#C0392B"
ROUGE_PALE = "#fbe9e7"
AMBRE = "#df8d20"
AMBRE_PALE = "#fff2df"
SURFACE = "#f4f7f8"
LIGNE = "#dce5e8"
ESTOMPE = "#6f8089"
BLANC = "#ffffff"

# Le vert et le marine sont proches en luminance : sur un écran en plein
# soleil, la hiérarchie se brouille. Le marine sert donc aux fonds et aux
# titres, le vert uniquement aux actions et aux montants positifs.

COULEUR_NIVEAU = {
    "bon": (VERT, MENTHE_PALE, "#cbe8d7"),
    "attention": ("#a86813", AMBRE_PALE, "#f3d5a7"),
    "alerte": (ROUGE, ROUGE_PALE, "#f5cdc7"),
    "info": (MARINE, "#e7f1f5", "#c9dfe8"),
}


# ---------------------------------------------------------------------------
# Feuille de style
# ---------------------------------------------------------------------------

_CSS = f"""
<style>
/* ---- Cadre général ---------------------------------------------------- */
.stApp {{ background: {SURFACE}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1180px; }}

h1, h2, h3 {{ color: {ENCRE}; letter-spacing: -.02em; }}
h1 {{ font-weight: 800; }}

/* Aucun texte sous 11px : la limite basse de lisibilite sur telephone. */
.dz-card, .dz-card * {{ font-size: inherit; }}

/* ---- Barre laterale --------------------------------------------------- */
section[data-testid="stSidebar"] {{ background: {BLANC}; border-right: 1px solid {LIGNE}; }}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem; }}

/* ---- Boutons ---------------------------------------------------------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border-radius: 12px; font-weight: 650; min-height: 44px;
  border: 1px solid {LIGNE}; transition: none;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: {VERT}; border-color: {VERT}; color: {BLANC};
}}
.stButton > button[kind="primary"]:hover {{ background: {VERT_CLAIR}; border-color: {VERT_CLAIR}; }}

/* ---- Champs ----------------------------------------------------------- */
.stTextInput input, .stNumberInput input, .stDateInput input,
div[data-baseweb="select"] > div {{
  border-radius: 12px !important; background: {SURFACE} !important;
  border-color: {LIGNE} !important; min-height: 42px;
}}

/* ---- Onglets ---------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {LIGNE}; }}
.stTabs [data-baseweb="tab"] {{
  height: 42px; padding: 0 14px; font-weight: 650; font-size: 14px; color: {ESTOMPE};
}}
.stTabs [aria-selected="true"] {{ color: {VERT}; }}

/* ---- Cartes ----------------------------------------------------------- */
.dz-card {{
  background: {BLANC}; border: 1px solid {LIGNE}; border-radius: 18px;
  padding: 14px 16px; margin-bottom: 10px;
}}
.dz-hero {{
  background: linear-gradient(145deg, {MARINE}, {MARINE_CLAIR});
  border-radius: 22px; padding: 20px 22px; color: {BLANC}; margin-bottom: 14px;
}}
.dz-hero .lab {{ font-size: 11px; letter-spacing: .09em; text-transform: uppercase;
  color: #a9c2cb; font-weight: 700; }}
.dz-hero .val {{ font-size: 34px; font-weight: 850; letter-spacing: -.04em; margin: 6px 0 2px; }}
.dz-hero .sub {{ font-size: 12px; color: #bad0d7; }}

.dz-kpi {{ background: {BLANC}; border: 1px solid {LIGNE}; border-radius: 14px; padding: 11px 13px; }}
.dz-kpi .t {{ font-size: 11px; color: {ESTOMPE}; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; }}
.dz-kpi .v {{ font-size: 20px; font-weight: 780; letter-spacing: -.03em; margin-top: 3px; }}
.dz-kpi .n {{ font-size: 11px; color: {ESTOMPE}; margin-top: 2px; }}

.dz-msg {{ border-radius: 16px; padding: 13px 15px; margin-bottom: 9px;
  display: flex; gap: 12px; align-items: flex-start; }}
.dz-msg .ic {{ width: 32px; height: 32px; flex: 0 0 32px; border-radius: 10px;
  display: grid; place-items: center; font-weight: 800; font-size: 15px; }}
.dz-msg .tt {{ font-size: 13px; font-weight: 750; margin-bottom: 3px; }}
.dz-msg .tx {{ font-size: 12px; line-height: 1.45; }}

.dz-line {{ display: flex; justify-content: space-between; align-items: center;
  gap: 10px; padding: 11px 0; border-bottom: 1px solid #edf1f2; }}
.dz-line:last-child {{ border-bottom: none; }}
.dz-line .l {{ font-size: 13px; font-weight: 700; }}
.dz-line .l small {{ display: block; font-size: 11px; font-weight: 400; color: {ESTOMPE}; margin-top: 2px; }}
.dz-line .r {{ font-size: 14px; font-weight: 750; text-align: right; white-space: nowrap; }}
.dz-line .r small {{ display: block; font-size: 11px; font-weight: 400; color: {ESTOMPE}; }}

.dz-tag {{ display: inline-block; font-size: 11px; font-weight: 700; border-radius: 6px;
  padding: 2px 7px; margin-left: 5px; }}

/* ---- Carte de scenario ------------------------------------------------ */
.dz-sc {{ background: {BLANC}; border: 1px solid {LIGNE}; border-radius: 18px;
  padding: 14px 16px; margin-bottom: 10px; }}
.dz-sc.ref {{ border-color: {MARINE}; }}
.dz-sc .nom {{ font-size: 14px; font-weight: 750; }}
.dz-sc .res {{ font-size: 12px; color: {ESTOMPE}; margin-top: 3px; line-height: 1.45; }}
.dz-sc .grille {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  border-top: 1px solid {LIGNE}; margin-top: 12px; padding-top: 11px; }}
.dz-sc .grille .t {{ font-size: 11px; color: {ESTOMPE}; text-transform: uppercase;
  letter-spacing: .04em; font-weight: 700; }}
.dz-sc .grille .v {{ font-size: 15px; font-weight: 750; margin-top: 3px; white-space: nowrap; }}

/* ---- Grille du calendrier --------------------------------------------- */
.dz-jour {{ border: 1px solid {LIGNE}; border-radius: 9px; padding: 5px 6px;
  min-height: 58px; background: {BLANC}; }}
.dz-jour .d {{ font-size: 11px; color: {ESTOMPE}; }}
.dz-jour .s {{ font-size: 13px; font-weight: 700; margin-top: 1px; }}
.dz-jour .m {{ font-size: 11px; color: {ESTOMPE}; }}
.dz-jour.vide {{ border-color: transparent; background: transparent; }}
.dz-jour.hors {{ background: {SURFACE}; border-style: dashed; }}
.dz-dow {{ font-size: 11px; font-weight: 700; color: {ESTOMPE}; text-align: center;
  padding-bottom: 4px; }}

/* ---- Telephone -------------------------------------------------------- */
@media (max-width: 640px) {{
  .block-container {{ padding: 1rem .8rem 5rem !important; }}
  h1 {{ font-size: 1.45rem !important; }}
  .dz-hero .val {{ font-size: 29px; }}
  .stTabs [data-baseweb="tab-list"] {{ overflow-x: auto; flex-wrap: nowrap;
    scrollbar-width: none; }}
  .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {{ display: none; }}
  .stTabs [data-baseweb="tab"] {{ white-space: nowrap; padding: 0 11px; }}
}}
</style>
"""


def appliquer() -> None:
    """À appeler une fois, juste après `st.set_page_config`."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Fabrication du HTML
# ---------------------------------------------------------------------------

def _e(valeur) -> str:
    """
    Échappe une valeur avant de l'insérer dans du HTML.

    Un nom de compte est saisi par l'utilisateur. Sans cette précaution,
    « <b>Alpha » casserait la mise en page, et pire pourrait passer.
    """
    return _html.escape(str(valeur), quote=True)


def hero(etiquette: str, valeur: str, note: str = "") -> None:
    """Le chiffre qui domine l'écran : solde projeté, trésorerie, total."""
    st.markdown(
        f'<div class="dz-hero"><div class="lab">{_e(etiquette)}</div>'
        f'<div class="val">{_e(valeur)}</div>'
        f'<div class="sub">{_e(note)}</div></div>',
        unsafe_allow_html=True)


def kpi(colonne, titre: str, valeur: str, note: str = "",
        couleur: str = ENCRE) -> None:
    """Un indicateur secondaire, dans une colonne."""
    colonne.markdown(
        f'<div class="dz-kpi"><div class="t">{_e(titre)}</div>'
        f'<div class="v" style="color:{couleur}">{_e(valeur)}</div>'
        f'<div class="n">{_e(note)}</div></div>',
        unsafe_allow_html=True)


def message(niveau: str, titre: str, texte: str) -> None:
    """
    Un encart d'analyse.

    Remplace `st.success` et consorts : le prototype les montre avec un
    titre et une explication, là où Streamlit n'affiche qu'une ligne.
    """
    couleur, fond, bord = COULEUR_NIVEAU.get(niveau, COULEUR_NIVEAU["info"])
    icone = {"bon": "✓", "attention": "!", "alerte": "!"}.get(niveau, "i")
    st.markdown(
        f'<div class="dz-msg" style="background:{fond};border:1px solid {bord}">'
        f'<div class="ic" style="color:{couleur};background:{BLANC}">{icone}</div>'
        f'<div><div class="tt" style="color:{couleur}"'
        f'{" style=margin-bottom:0" if not texte else ""}>{_e(titre)}</div>'
        + (f'<div class="tx" style="color:{ENCRE}">{_e(texte)}</div>'
           if texte else "")
        + '</div></div>',
        unsafe_allow_html=True)


def ligne(gauche: str, droite: str, sous_gauche: str = "",
          sous_droite: str = "", couleur: str = ENCRE) -> str:
    """Une ligne de liste. Rend le HTML : à regrouper dans un `dz-card`."""
    sg = f"<small>{_e(sous_gauche)}</small>" if sous_gauche else ""
    sd = f"<small>{_e(sous_droite)}</small>" if sous_droite else ""
    return (f'<div class="dz-line"><div class="l">{_e(gauche)}{sg}</div>'
            f'<div class="r" style="color:{couleur}">{_e(droite)}{sd}</div></div>')


def carte(contenu_html: str) -> None:
    """Encadre du HTML déjà fabriqué — typiquement une suite de `ligne`."""
    st.markdown(f'<div class="dz-card">{contenu_html}</div>',
                unsafe_allow_html=True)


def message_phrase(niveau: str, phrase: str) -> None:
    """
    Affiche une phrase du moteur en encart.

    Les messages sont ecrits « Constat. Explication. » : la premiere
    phrase sert de titre, le reste de corps. Quand il n'y a qu'une phrase,
    elle reste seule — la repeter en titre et en corps, comme une premiere
    version le faisait, donne un encart qui se lit deux fois.
    """
    titre, separateur, suite = phrase.partition(". ")
    if separateur:
        message(niveau, titre + ".", suite)
    else:
        message(niveau, phrase, "")


def scenario(nom: str, resume: str, colonnes: list[tuple[str, str, str]],
             reference: bool = False) -> None:
    """
    Une carte de scénario : son nom, son hypothèse, et trois résultats.

    `colonnes` est une suite de (titre, valeur, couleur). Trois au plus :
    au-delà, la grille se casse sur un téléphone.
    """
    cases = "".join(
        f'<div><div class="t">{_e(t)}</div>'
        f'<div class="v" style="color:{c}">{_e(v)}</div></div>'
        for t, v, c in colonnes[:3])
    st.markdown(
        f'<div class="dz-sc{" ref" if reference else ""}">'
        f'<div class="nom">{_e(nom)}</div>'
        f'<div class="res">{_e(resume)}</div>'
        f'<div class="grille">{cases}</div></div>',
        unsafe_allow_html=True)


def couleur_montant(valeur) -> str:
    """Vert au-dessus de zéro, rouge en dessous, encre à zéro."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return ENCRE
    if nombre > 0:
        return VERT
    if nombre < 0:
        return ROUGE
    return ENCRE
