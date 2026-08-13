"""
LANGUES — français, anglais, espagnol, chinois
PrevuFlow — SMD Global Consulting LLC

Une application vendue à l'international ne peut pas être une application
française traduite après coup. Ce module pose la règle inverse : les données
sont neutres, et la langue ne décide que de la présentation.

Ce qui dépend de la langue, et qu'on oublie souvent
---------------------------------------------------
Traduire les mots ne suffit pas. Le même montant s'écrit :

    français   1 234,56 €          espace fine, virgule décimale, symbole après
    anglais    $1,234.56           virgule milliers, point décimal, symbole avant
    espagnol   1.234,56 €          point milliers, virgule décimale
    chinois    ¥1,234.56           symbole avant, date 2026年8月7日

Un utilisateur espagnol qui lit « 1.234,56 » comprend mille deux cent
trente-quatre. Un anglophone lit « un virgule deux ». Se tromper là-dessus
sur une application financière, c'est perdre la confiance en un coup d'œil.

Module pur : aucune dépendance à Streamlit, aucun accès réseau.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

DOSSIER_TRADUCTIONS = Path(__file__).parent / "traductions"
LANGUE_PAR_DEFAUT = "fr"


class ErreurLangue(Exception):
    pass


# ---------------------------------------------------------------------------
# Ce qui caractérise une langue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Locale:
    """
    Une langue et ses conventions d'écriture.

    `code` suit BCP-47 : « fr », « en », « es », « zh ». On reste sur la
    langue seule et non la région — distinguer en-GB de en-US n'apporterait
    rien tant que les textes sont identiques.
    """
    code: str
    nom_natif: str          # comme l'utilisateur le lit dans le sélecteur
    nom_francais: str
    drapeau: str

    separateur_milliers: str
    separateur_decimal: str
    symbole_avant: bool     # $1 234 plutôt que 1 234 €
    espace_avant_symbole: bool

    format_date: str        # motif strftime
    premier_jour_semaine: int   # 0 = lundi, 6 = dimanche
    droite_a_gauche: bool = False


LOCALES: dict[str, Locale] = {
    "fr": Locale(
        code="fr", nom_natif="Français", nom_francais="Français", drapeau="🇫🇷",
        # Espace fine insécable : un montant ne doit pas se couper en fin de ligne.
        separateur_milliers=" ", separateur_decimal=",",
        symbole_avant=False, espace_avant_symbole=True,
        format_date="%d/%m/%Y", premier_jour_semaine=0),

    "en": Locale(
        code="en", nom_natif="English", nom_francais="Anglais", drapeau="🇬🇧",
        separateur_milliers=",", separateur_decimal=".",
        symbole_avant=True, espace_avant_symbole=False,
        # Format international ISO plutôt que le format américain m/j/a,
        # ambigu pour tout le reste du monde.
        format_date="%d %b %Y", premier_jour_semaine=6),

    "es": Locale(
        code="es", nom_natif="Español", nom_francais="Espagnol", drapeau="🇪🇸",
        separateur_milliers=".", separateur_decimal=",",
        symbole_avant=False, espace_avant_symbole=True,
        format_date="%d/%m/%Y", premier_jour_semaine=0),

    "zh": Locale(
        code="zh", nom_natif="中文", nom_francais="Chinois", drapeau="🇨🇳",
        separateur_milliers=",", separateur_decimal=".",
        symbole_avant=True, espace_avant_symbole=False,
        format_date="%Y年%m月%d日", premier_jour_semaine=0),
}

LANGUES_DISPONIBLES = list(LOCALES)


def locale(code: str | None = None) -> Locale:
    return LOCALES.get((code or LANGUE_PAR_DEFAUT).lower()[:2],
                       LOCALES[LANGUE_PAR_DEFAUT])


def detecter(entete_navigateur: str | None) -> str:
    """
    Devine la langue depuis l'en-tête du navigateur.

    « fr-FR,fr;q=0.9,en-US;q=0.8 » donne « fr ». Une langue inconnue
    retombe sur le français plutôt que d'échouer : mieux vaut une langue
    par défaut qu'un écran vide.
    """
    if not entete_navigateur:
        return LANGUE_PAR_DEFAUT
    for morceau in entete_navigateur.split(","):
        code = morceau.split(";")[0].strip().lower()[:2]
        if code in LOCALES:
            return code
    return LANGUE_PAR_DEFAUT


# ---------------------------------------------------------------------------
# Nombres, montants, dates
# ---------------------------------------------------------------------------

def formater_nombre(valeur, decimales: int = 2, code: str | None = None) -> str:
    """Applique les séparateurs de la langue à un nombre."""
    l = locale(code)
    if not isinstance(valeur, Decimal):
        valeur = Decimal(str(valeur))

    negatif = valeur < 0
    texte = f"{abs(valeur):,.{decimales}f}"          # toujours 1,234.56 au départ
    entier, _, fraction = texte.partition(".")

    # On passe par des marqueurs : remplacer directement provoquerait des
    # collisions quand les deux séparateurs sont « , » et « . » inversés.
    entier = entier.replace(",", "\x00")
    resultat = entier.replace("\x00", l.separateur_milliers)
    if decimales > 0 and fraction:
        resultat += l.separateur_decimal + fraction
    return ("-" if negatif else "") + resultat


def formater_montant(valeur, devise: str, code: str | None = None,
                     avec_decimales: bool = True) -> str:
    """
    « 1 234,56 € » en français, « $1,234.56 » en anglais.

    Le nombre de décimales vient toujours de la devise, jamais de la langue :
    le yen n'a pas de centimes, quelle que soit la langue de lecture.
    """
    from argent import decimales as decimales_devise, symbole

    l = locale(code)
    n = decimales_devise(devise) if avec_decimales else 0
    nombre = formater_nombre(valeur, n, code)
    sym = symbole(devise)

    if l.symbole_avant:
        espace = " " if l.espace_avant_symbole else ""
        # Le signe reste devant le tout : -$1,234.56 et non $-1,234.56
        if nombre.startswith("-"):
            return f"-{sym}{espace}{nombre[1:]}"
        return f"{sym}{espace}{nombre}"

    espace = " " if l.espace_avant_symbole else ""
    return f"{nombre}{espace}{sym}"


def formater_date(jour: date, code: str | None = None) -> str:
    l = locale(code)
    if l.code == "en":
        # strftime rend les mois dans la langue du système : on les fixe.
        mois = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return f"{jour.day:02d} {mois[jour.month - 1]} {jour.year}"
    return jour.strftime(l.format_date)


MOIS = {
    "fr": ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
           "Août", "Septembre", "Octobre", "Novembre", "Décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
           "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
    "zh": ["一月", "二月", "三月", "四月", "五月", "六月", "七月",
           "八月", "九月", "十月", "十一月", "十二月"],
}

JOURS_COURTS = {
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    "zh": ["一", "二", "三", "四", "五", "六", "日"],
}


def nom_mois(numero: int, code: str | None = None) -> str:
    return MOIS.get(locale(code).code, MOIS["fr"])[numero - 1]


def jours_semaine(code: str | None = None) -> list[str]:
    """
    Les jours dans l'ordre d'affichage du calendrier.

    L'anglais commence la semaine le dimanche : afficher un calendrier qui
    démarre le lundi à un Américain, c'est le désorienter à chaque lecture.
    """
    l = locale(code)
    jours = JOURS_COURTS.get(l.code, JOURS_COURTS["fr"])
    if l.premier_jour_semaine == 6:
        return [jours[6]] + jours[:6]
    return jours


# ---------------------------------------------------------------------------
# Textes
# ---------------------------------------------------------------------------

_cache: dict[str, dict] = {}


def _charger(code: str) -> dict:
    if code in _cache:
        return _cache[code]
    chemin = DOSSIER_TRADUCTIONS / f"{code}.json"
    try:
        _cache[code] = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache[code] = {}
    return _cache[code]


def traduire(cle: str, code: str | None = None, **variables) -> str:
    """
    Rend le texte associé à une clé.

    Trois niveaux de repli, pour qu'un texte manquant n'efface jamais un
    écran : la langue demandée, puis le français, puis la clé elle-même.
    Voir « home.solde » à l'écran est laid, mais reste plus utile qu'un vide.
    """
    code = (code or LANGUE_PAR_DEFAUT).lower()[:2]
    texte = _charger(code).get(cle)
    if texte is None and code != LANGUE_PAR_DEFAUT:
        texte = _charger(LANGUE_PAR_DEFAUT).get(cle)
    if texte is None:
        return cle
    if variables:
        try:
            return texte.format(**variables)
        except (KeyError, IndexError):
            return texte            # variable absente : on rend le texte brut
    return texte


def pluriel(cle_singulier: str, cle_pluriel: str, nombre: int,
            code: str | None = None, **variables) -> str:
    """
    Choisit entre singulier et pluriel.

    Le chinois n'accorde pas : la même forme sert pour un et pour mille.
    Le français met au singulier à zéro (« 0 facture »), l'anglais au
    pluriel (« 0 invoices »).
    """
    l = locale(code)
    if l.code == "zh":
        cle = cle_pluriel
    elif l.code == "fr":
        cle = cle_singulier if abs(nombre) < 2 else cle_pluriel
    else:
        cle = cle_singulier if abs(nombre) == 1 else cle_pluriel
    return traduire(cle, code, nombre=nombre, **variables)


def cles_manquantes(code: str) -> list[str]:
    """Ce qui reste à traduire, comparé au français."""
    reference = set(_charger(LANGUE_PAR_DEFAUT))
    return sorted(reference - set(_charger(code)))


def couverture(code: str) -> float:
    """Part des textes traduits, en pourcentage."""
    reference = _charger(LANGUE_PAR_DEFAUT)
    if not reference:
        return 100.0
    manquantes = len(cles_manquantes(code))
    return round((len(reference) - manquantes) / len(reference) * 100, 1)


def vider_cache() -> None:
    """Utile aux tests et après modification d'un fichier de traduction."""
    _cache.clear()
