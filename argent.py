"""
ARGENT — montants, devises et taux de change
PrevuFlow — SMD Global Consulting LLC

Corrige trois défauts identifiés par l'audit d'architecture :

  1. un montant ne portait pas sa devise, donc rien n'empêchait d'additionner
     des euros et des dollars ;
  2. les taux de change étaient écrits en dur, sans date ni source, donc
     impossibles à justifier ;
  3. une conversion ne rendait pas le taux employé, donc le total consolidé
     n'était pas explicable.

Module pur : aucune dépendance à Streamlit, pandas, fichier ou réseau.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN


def _texte(cle: str, **variables) -> str:
    """
    Repli quand l'appelant ne fournit pas sa propre traduction.

    Ce module reste pur : il ne connait ni Streamlit ni la langue de
    lecture. Ces messages sont des erreurs — rares, mais lues par
    l'utilisateur au pire moment.
    """
    from langues import traduire
    try:
        import streamlit as st
        code = st.session_state.get("langue", "fr")
    except Exception:
        code = "fr"
    return traduire(cle, code, **variables)


class ErreurArgent(ValueError):
    """Violation d'une règle monétaire. Le message est destiné à l'utilisateur."""


# ---------------------------------------------------------------------------
# Devises
# ---------------------------------------------------------------------------

# Nombre de décimales par devise. Ne jamais supposer « deux » :
# le yen n'en a aucune, le dinar koweïtien en a trois.
DECIMALES: dict[str, int] = {
    "EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "CAD": 2, "AUD": 2,
    "MAD": 2, "TRY": 2, "NGN": 2, "AED": 2, "CNY": 2, "ZAR": 2,
    "JPY": 0, "XOF": 0, "XAF": 0, "KRW": 0, "CLP": 0, "ISK": 0,
    "KWD": 3, "BHD": 3, "OMR": 3, "TND": 3,
}

SYMBOLES: dict[str, str] = {
    "EUR": "€", "USD": "$", "GBP": "£", "JPY": "¥", "CHF": "CHF",
    "CAD": "C$", "AUD": "A$", "XOF": "FCFA", "XAF": "FCFA", "MAD": "DH",
    "TRY": "₺", "NGN": "₦", "AED": "AED", "CNY": "¥", "ZAR": "R",
    "KWD": "KD", "TND": "DT",
}

NOMS: dict[str, str] = {
    "EUR": "Euro", "USD": "Dollar américain", "GBP": "Livre sterling",
    "JPY": "Yen", "CHF": "Franc suisse", "CAD": "Dollar canadien",
    "AUD": "Dollar australien", "XOF": "Franc CFA (UEMOA)",
    "XAF": "Franc CFA (CEMAC)", "MAD": "Dirham marocain",
    "TRY": "Livre turque", "NGN": "Naira", "AED": "Dirham des Émirats",
    "CNY": "Yuan", "ZAR": "Rand", "KWD": "Dinar koweïtien",
    "TND": "Dinar tunisien",
}


def decimales(devise: str) -> int:
    return DECIMALES.get(devise.upper(), 2)


def symbole(devise: str) -> str:
    return SYMBOLES.get(devise.upper(), devise.upper())


def nom_devise(devise: str) -> str:
    d = devise.upper()
    return NOMS.get(d, d)


def valider_devise(devise: str) -> str:
    """Un code ISO 4217 fait trois lettres. Rien d'autre n'est accepté."""
    d = str(devise).strip().upper()
    if len(d) != 3 or not d.isalpha():
        raise ErreurArgent(
            f"« {devise} » n'est pas un code devise valide. "
            f"Attendu : trois lettres, par exemple EUR, USD ou XOF.")
    return d


# ---------------------------------------------------------------------------
# Montant
# ---------------------------------------------------------------------------

# Typographie française : espace fine insécable entre les milliers, espace
# insécable avant le symbole. Nommées, parce qu'un caractère invisible dans
# le code est un piège pour la personne qui relira ce fichier.
ESPACE_MILLIERS = "\u202f"      # espace fine insécable
ESPACE_DEVISE = "\u00a0"        # espace insécable

@dataclass(frozen=True)
class Montant:
    """
    Une somme et sa devise, indissociables.

    C'est la correction du défaut principal : additionner deux devises
    différentes lève désormais une erreur au lieu de produire un chiffre faux.

    >>> Montant(Decimal("10"), "EUR") + Montant(Decimal("5"), "EUR")
    Montant(valeur=Decimal('15'), devise='EUR')
    """
    valeur: Decimal
    devise: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "devise", valider_devise(self.devise))
        if not isinstance(self.valeur, Decimal):
            object.__setattr__(self, "valeur", Decimal(str(self.valeur)))
        if not self.valeur.is_finite():
            raise ErreurArgent(_texte("arg.montant_fini"))

    # ---- Construction --------------------------------------------------

    @classmethod
    def zero(cls, devise: str) -> "Montant":
        return cls(Decimal("0"), devise)

    @classmethod
    def de(cls, valeur, devise: str) -> "Montant":
        """Accepte int, float, str ou Decimal. Le float passe par str : sinon
        0.1 devient 0.1000000000000000055511151231257827."""
        return cls(Decimal(str(valeur)), devise)

    # ---- Arithmétique --------------------------------------------------

    def _meme_devise(self, autre: "Montant") -> None:
        if self.devise != autre.devise:
            raise ErreurArgent(
                f"Impossible d'additionner {self.devise} et {autre.devise} "
                f"sans conversion. Convertissez d'abord dans une devise commune.")

    def __add__(self, autre: "Montant") -> "Montant":
        self._meme_devise(autre)
        return Montant(self.valeur + autre.valeur, self.devise)

    def __sub__(self, autre: "Montant") -> "Montant":
        self._meme_devise(autre)
        return Montant(self.valeur - autre.valeur, self.devise)

    def __neg__(self) -> "Montant":
        return Montant(-self.valeur, self.devise)

    def __abs__(self) -> "Montant":
        return Montant(abs(self.valeur), self.devise)

    def __mul__(self, facteur) -> "Montant":
        return Montant(self.valeur * Decimal(str(facteur)), self.devise)

    __rmul__ = __mul__

    def __lt__(self, autre: "Montant") -> bool:
        self._meme_devise(autre)
        return self.valeur < autre.valeur

    def __le__(self, autre: "Montant") -> bool:
        self._meme_devise(autre)
        return self.valeur <= autre.valeur

    # ---- Lecture -------------------------------------------------------

    @property
    def arrondi(self) -> Decimal:
        """Arrondi au nombre de décimales de la devise, en demi-pair.

        Le demi-pair (ROUND_HALF_EVEN) est la règle bancaire : elle ne
        favorise systématiquement ni le débiteur ni le créancier.
        """
        quantum = Decimal(1).scaleb(-decimales(self.devise))
        return self.valeur.quantize(quantum, rounding=ROUND_HALF_EVEN)

    @property
    def negatif(self) -> bool:
        return self.valeur < 0

    @property
    def nul(self) -> bool:
        return self.valeur == 0

    def formater(self, avec_decimales: bool = True) -> str:
        """
        « 1 234,56 € » selon la typographie française.

        Deux espaces insécables différentes, et ce n'est pas un détail :
        sans elles, un affichage peut couper « 1 234,56 € » en fin de ligne
        et montrer « 1 » d'un côté, « 234,56 € » de l'autre.
        """
        n = decimales(self.devise) if avec_decimales else 0
        texte = (f"{abs(self.arrondi):,.{n}f}"
                 .replace(",", ESPACE_MILLIERS)
                 .replace(".", ","))
        signe = "-" if self.negatif else ""
        return f"{signe}{texte}{ESPACE_DEVISE}{symbole(self.devise)}"

    def __str__(self) -> str:
        return self.formater()


def somme(montants, devise: str) -> Montant:
    """
    Additionne une suite de montants. La devise attendue est exigée en
    argument : sur une liste vide, il n'y a aucun moyen de la deviner.
    """
    total = Montant.zero(devise)
    for m in montants:
        total = total + m
    return total


# ---------------------------------------------------------------------------
# Taux de change
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Taux:
    """
    Un taux daté et sourcé. Sans ces deux informations, un montant converti
    n'est pas justifiable — c'est le défaut que corrige cette classe.

    `valeur` exprime : 1 unité de `base` vaut `valeur` unités de `contre`.
    """
    base: str
    contre: str
    valeur: Decimal
    observe_le: date
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", valider_devise(self.base))
        object.__setattr__(self, "contre", valider_devise(self.contre))
        if not isinstance(self.valeur, Decimal):
            object.__setattr__(self, "valeur", Decimal(str(self.valeur)))
        if self.base == self.contre:
            raise ErreurArgent(_texte("arg.taux_deux_devises"))
        if self.valeur <= 0 or not self.valeur.is_finite():
            raise ErreurArgent("Un taux de change est strictement positif.")
        if not self.source:
            raise ErreurArgent(_texte("arg.taux_sans_source"))

    @property
    def inverse(self) -> "Taux":
        return Taux(self.contre, self.base, Decimal("1") / self.valeur,
                    self.observe_le, self.source)

    def anciennete(self, au: date | None = None) -> int:
        return ((au or date.today()) - self.observe_le).days

    def phrase(self) -> str:
        return (f"1 {self.base} = {self.valeur.normalize():f} {self.contre} "
                f"· {self.observe_le.strftime('%d/%m/%Y')} · {self.source}")


@dataclass(frozen=True)
class Conversion:
    """
    Le résultat d'une conversion, accompagné du taux employé.

    L'audit exige que l'utilisateur puisse voir « les taux utilisés et
    l'horodatage de conversion ». Rendre le taux avec le résultat est la
    seule façon de tenir cette exigence sans le reconstituer plus tard.
    """
    origine: Montant
    resultat: Montant
    taux: Taux | None          # None si aucune conversion n'a eu lieu

    @property
    def convertie(self) -> bool:
        return self.taux is not None

    def phrase(self) -> str:
        if self.taux is None:
            return f"{self.origine.formater()} — aucune conversion"
        return (f"{self.origine.formater()} → {self.resultat.formater()} "
                f"({self.taux.phrase()})")


class TableTaux:
    """
    Les taux connus de l'application, chacun daté et sourcé.

    Un taux manquant lève une erreur explicite : mieux vaut refuser un total
    que d'en afficher un faux.
    """

    def __init__(self, taux: list[Taux] | None = None) -> None:
        self._taux: dict[tuple[str, str], Taux] = {}
        for t in taux or []:
            self.ajouter(t)

    def ajouter(self, taux: Taux) -> "TableTaux":
        """Le taux le plus récent l'emporte pour une même paire."""
        cle = (taux.base, taux.contre)
        connu = self._taux.get(cle)
        if connu is None or taux.observe_le >= connu.observe_le:
            self._taux[cle] = taux
            self._taux[(taux.contre, taux.base)] = taux.inverse
        return self

    def trouver(self, base: str, contre: str) -> Taux | None:
        """
        Cherche un taux direct, puis à défaut un passage par une devise pivot.

        Sans cette triangulation, quelqu'un qui détient des livres et des
        dollars — mais dont les taux sont tous exprimés vers l'euro — ne
        pourrait pas consolider en dollars. C'est un cas courant, pas un cas
        limite : les tables de taux sont presque toujours pivotées sur une
        seule devise.
        """
        base, contre = valider_devise(base), valider_devise(contre)
        if base == contre:
            return None

        direct = self._taux.get((base, contre))
        if direct is not None:
            return direct

        # GBP → USD n'existe pas, mais GBP → EUR et EUR → USD, oui.
        for pivot in self.devises_connues:
            if pivot in (base, contre):
                continue
            vers_pivot = self._taux.get((base, pivot))
            depuis_pivot = self._taux.get((pivot, contre))
            if vers_pivot is None or depuis_pivot is None:
                continue
            # Le taux dérivé porte la date la plus ancienne des deux : c'est
            # elle qui détermine la fraîcheur réelle du résultat.
            return Taux(
                base=base,
                contre=contre,
                valeur=vers_pivot.valeur * depuis_pivot.valeur,
                observe_le=min(vers_pivot.observe_le, depuis_pivot.observe_le),
                source=f"calculé via {pivot} ({vers_pivot.source}, "
                       f"{depuis_pivot.source})")
        return None

    def convertir(self, montant: Montant, vers: str) -> Conversion:
        vers = valider_devise(vers)
        if montant.devise == vers:
            return Conversion(montant, montant, None)

        taux = self.trouver(montant.devise, vers)
        if taux is None:
            raise ErreurArgent(
                f"Aucun taux connu pour convertir {montant.devise} en {vers}. "
                f"Ajoutez-le dans les réglages, ou choisissez une autre "
                f"devise de référence.")

        return Conversion(montant, Montant(montant.valeur * taux.valeur, vers), taux)

    def consolider(self, montants: list[Montant], vers: str) -> tuple[Montant, list[Taux]]:
        """
        Additionne des montants de devises différentes dans une devise unique,
        et rend la liste des taux employés pour que le total soit explicable.
        """
        vers = valider_devise(vers)
        total = Montant.zero(vers)
        employes: dict[tuple[str, str], Taux] = {}
        for m in montants:
            c = self.convertir(m, vers)
            total = total + c.resultat
            if c.taux is not None:
                employes[(c.taux.base, c.taux.contre)] = c.taux
        return total, list(employes.values())

    @property
    def devises_connues(self) -> set[str]:
        return {d for paire in self._taux for d in paire}

    def plus_ancien(self) -> Taux | None:
        vus = {(t.base, t.contre) if t.base < t.contre else (t.contre, t.base): t
               for t in self._taux.values()}
        return min(vus.values(), key=lambda t: t.observe_le, default=None)


# ---------------------------------------------------------------------------
# Table de repli
# ---------------------------------------------------------------------------

# Ces valeurs sont des ordres de grandeur saisis manuellement, PAS une
# cotation de marché. Elles portent leur date et leur source pour que
# l'utilisateur sache exactement ce qu'il regarde. Un écran de réglage
# doit permettre de les corriger.
_SOURCE_REPLI = "saisie manuelle"
_DATE_REPLI = date(2026, 8, 1)

_REPLI_VERS_EUR: dict[str, str] = {
    "USD": "0.92", "GBP": "1.17", "CHF": "1.06", "CAD": "0.68",
    "AUD": "0.61", "JPY": "0.0061", "XOF": "0.001524", "XAF": "0.001524",
    "MAD": "0.092", "TRY": "0.026", "NGN": "0.00060", "AED": "0.25",
    "CNY": "0.13", "ZAR": "0.051",
}


def table_par_defaut() -> TableTaux:
    """Table de repli, utilisable immédiatement et corrigeable par l'utilisateur."""
    return TableTaux([
        Taux(devise, "EUR", Decimal(valeur), _DATE_REPLI, _SOURCE_REPLI)
        for devise, valeur in _REPLI_VERS_EUR.items()
    ])


DEVISES_PROPOSEES: list[str] = ["EUR", "USD", "GBP", "XOF", "XAF", "MAD",
                                "CHF", "CAD", "AED", "TRY", "NGN", "CNY",
                                "JPY", "ZAR", "AUD"]
