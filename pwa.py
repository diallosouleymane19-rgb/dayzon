"""
PWA — Dayzon installable sur smartphone
Dayzon — SMD Global Consulting LLC

Rend l'application installable depuis le navigateur : icône sur l'écran
d'accueil, plein écran, sans passer par l'App Store ni Google Play.

Comment cela fonctionne, et pourquoi c'est fait ainsi
----------------------------------------------------
Streamlit ne permet pas d'écrire directement dans le `<head>` de la page.
Le seul point d'entrée est un composant HTML, rendu dans un cadre isolé.
On y place donc un court script qui remonte au document parent pour y
insérer le manifeste et les balises nécessaires.

C'est un contournement, et il est assumé : il n'existe pas d'autre voie
sans modifier Streamlit lui-même. Le script est volontairement court,
sans dépendance, et ne s'exécute qu'une fois par session.

Aucun service worker n'est enregistré. Un service worker met des fichiers
en cache ; sur une application qui traite des relevés bancaires, cela
reviendrait à laisser des traces sur l'appareil sans que l'utilisateur
l'ait demandé. L'installation fonctionne sans lui.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components   # st.iframe dans les versions récentes

COULEUR_THEME = "#123e53"

_SCRIPT = """
<script>
(function () {
  // Le composant vit dans un cadre isolé ; la vraie page est au-dessus.
  var doc = window.parent && window.parent.document;
  if (!doc || doc.getElementById('dayzon-pwa')) return;

  var marqueur = doc.createElement('meta');
  marqueur.id = 'dayzon-pwa';
  marqueur.name = 'dayzon-pwa';
  marqueur.content = '1';
  doc.head.appendChild(marqueur);

  function ajouter(balise, attributs) {
    var e = doc.createElement(balise);
    for (var k in attributs) e.setAttribute(k, attributs[k]);
    doc.head.appendChild(e);
  }

  ajouter('link', {rel: 'manifest', href: 'app/static/manifest.json'});

  // iOS ignore le manifeste : il lui faut ses propres balises.
  ajouter('meta', {name: 'apple-mobile-web-app-capable', content: 'yes'});
  ajouter('meta', {name: 'apple-mobile-web-app-title', content: 'Dayzon'});
  ajouter('meta', {name: 'apple-mobile-web-app-status-bar-style',
                   content: 'black-translucent'});
  ajouter('link', {rel: 'apple-touch-icon',
                   href: 'app/static/apple-touch-icon.png'});

  ajouter('meta', {name: 'theme-color', content: '__COULEUR__'});
  ajouter('meta', {name: 'mobile-web-app-capable', content: 'yes'});

  // Sur mobile, empêche le zoom involontaire au double-tap dans les tableaux.
  var vp = doc.querySelector('meta[name="viewport"]');
  if (vp) vp.setAttribute('content',
    'width=device-width, initial-scale=1, viewport-fit=cover');
})();
</script>
"""

_STYLE_MOBILE = """
<style>
/* Confort de lecture sur téléphone. Aucune règle ne change les chiffres,
   seulement leur présentation. */
@media (max-width: 640px) {
  .block-container { padding: 1rem 0.8rem 5rem !important; }
  h1 { font-size: 1.45rem !important; line-height: 1.15 !important; }
  h2 { font-size: 1.15rem !important; }
  h3 { font-size: 1rem !important; }

  /* Les onglets deviennent défilables plutôt que compressés :
     cinq onglets ne tiennent pas sur un écran de téléphone. */
  .stTabs [data-baseweb="tab-list"] {
    overflow-x: auto; flex-wrap: nowrap;
    scrollbar-width: none; -ms-overflow-style: none;
  }
  .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
  .stTabs [data-baseweb="tab"] { white-space: nowrap; padding: 0 12px; }

  /* Les indicateurs restent lisibles sans déborder. */
  [data-testid="stMetricValue"] { font-size: 1.15rem !important; }
  [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }

  /* Une cible tactile fait au moins 44 points de côté. */
  .stButton button, .stDownloadButton button { min-height: 44px; }
}

/* En mode installé, l'application occupe tout l'écran : on récupère
   l'espace sous l'encoche et au-dessus de la barre d'accueil. */
@media (display-mode: standalone) {
  .block-container {
    padding-top: max(1rem, env(safe-area-inset-top)) !important;
    padding-bottom: max(2rem, env(safe-area-inset-bottom)) !important;
  }
  header[data-testid="stHeader"] { height: env(safe-area-inset-top); }
}
</style>
"""


def _html_invisible(code: str) -> None:
    """
    Insère un fragment HTML sans occuper de place visible.

    Streamlit a renommé `components.html` en `st.iframe`. On préfère le
    nouveau nom quand il existe, sans casser les versions antérieures :
    l'application doit tourner aussi bien en local que sur l'hébergeur,
    dont les versions ne sont jamais identiques.

    Hauteur de 1 pixel et non 0 : `st.iframe` refuse une hauteur nulle.
    """
    try:
        if hasattr(st, "iframe"):
            st.iframe(code, height=1)
        else:
            components.html(code, height=1)
    except Exception:
        # Le script n'est qu'un confort d'installation. S'il échoue,
        # l'application doit continuer de fonctionner normalement.
        pass


def activer() -> None:
    """
    À appeler une fois, juste après `st.set_page_config`.

    Sans effet en local si le dossier `static/` n'est pas servi : la
    configuration `enableStaticServing` doit être active, ce qui est fait
    dans `.streamlit/config.toml`.
    """
    _html_invisible(_SCRIPT.replace("__COULEUR__", COULEUR_THEME))
    st.markdown(_STYLE_MOBILE, unsafe_allow_html=True)


def message_installation() -> None:
    """
    Explique comment installer l'application, une seule fois, et seulement
    si elle ne l'est pas déjà.

    Placé dans le panneau latéral plutôt qu'en pleine page : une invitation
    à installer qui recouvre l'écran au premier usage est une gêne, pas un
    service.
    """
    if st.session_state.get("_pwa_message_vu"):
        return
    st.session_state._pwa_message_vu = True

    import commun
    with st.expander(commun.t("pwa.installer")):
        st.markdown(commun.t("pwa.aide"))
