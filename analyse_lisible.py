"""
ANALYSE FINANCIERE EN LANGAGE CLAIR
PrevuFlow — SMD Global Consulting LLC

Transforme une liste d'operations brutes en informations qu'un dirigeant
comprend sans formation comptable.

Principe : on ne dit pas « recurrence quotidienne, regularite 82 % ».
On dit « Courses : environ 140 EUR par mois, 12 achats le mois dernier ».
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def _sans_accent(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _arr(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Categories — particuliers et entreprises
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, list[str]] = {
    # Entrees
    "Salaires et revenus": ["SALAIRE", "PAIE", "VIREMENT DE POLE", "REMUNERATION",
                             "TRAITEMENT", "SALARY", "PAYROLL"],
    "Encaissements clients": ["VIREMENT DE", "VIR RECU", "REGLEMENT", "PAIEMENT CLIENT",
                               "FACTURE", "STRIPE", "PAYPAL EUROPE", "SUMUP", "VERSEMENT"],
    "Aides et allocations": ["CAF ", "ALLOCATION", "APL", "POLE EMPLOI", "FRANCE TRAVAIL",
                              "PENSION", "RETRAITE", "SECU", "CPAM", "AMELI"],

    # Sorties — vie courante
    "Logement": ["LOYER", "SCI ", "FONCIA", "NEXITY", "CITYA", "HABITATION", "SYNDIC",
                  "RENT", "CHARGES COPRO"],
    "Énergie et eau": ["EDF", "ENGIE", "TOTALENERGIES", "TOTAL ENERGIES", "VEOLIA",
                        "SUEZ", "EAU ", "GAZ ", "ELECTRICITE"],
    "Courses alimentaires": ["CARREFOUR", "LECLERC", "INTERMARCHE", "LIDL", "ALDI",
                              "AUCHAN", "CASINO", "MONOPRIX", "FRANPRIX", "SUPER U",
                              "SUPERMARCHE", "MARKET", "GRAND FRAIS", "PICARD",
                              "BOULANGERIE", "FOURNIL", "BOUCHERIE", "PRIMEUR"],
    "Restaurants et sorties": ["RESTAURANT", "BRASSERIE", "PIZZ", "KEBAB", "MCDO",
                                "BURGER", "SUSHI", "BAR ", "CAFE ", "PAILLOTE",
                                "UBER EATS", "DELIVEROO", "JUST EAT"],
    "Transport et carburant": ["SNCF", "RATP", "TOTAL", "ESSO", "SHELL", "BP ", "AVIA",
                                "STATION", "CARBURANT", "PEAGE", "AUTOROUTE", "UBER",
                                "TAXI", "PARKING", "BLABLACAR", "TRAINLINE"],
    "Téléphone et internet": ["ORANGE", "SFR", "BOUYGUES", "FREE ", "SOSH", "RED BY",
                               "INTERNET", "FIBRE", "MOBILE", "TELECOM"],
    "Abonnements et logiciels": ["NETFLIX", "SPOTIFY", "DEEZER", "AMAZON PRIME", "DISNEY",
                                  "CANAL", "ABONNEMENT", "MICROSOFT", "GOOGLE", "ADOBE",
                                  "OPENAI", "ANTHROPIC", "OVH", "GITHUB", "NOTION",
                                  "SUBSCRIPTION", "SAAS"],
    "Achats et équipement": ["AMAZON", "FNAC", "DARTY", "BOULANGER", "KIABI", "ACTION",
                              "DECATHLON", "IKEA", "LEROY MERLIN", "CDISCOUNT", "ZALANDO",
                              "SHEIN", "TEMU", "KLARNA"],
    "Santé": ["PHARMACIE", "MEDECIN", "DOCTEUR", "MUTUELLE", "DENTISTE", "LABORATOIRE",
               "OPTIQUE", "HOPITAL", "CLINIQUE"],
    "Assurances": ["ASSURANCE", "AXA", "MAIF", "MACIF", "MAAF", "ALLIANZ", "GENERALI",
                    "GROUPAMA", "MATMUT", "GMF", "INSURANCE"],
    "Banque et crédits": ["CREDIT", "PRET", "MENSUALITE", "AGIOS", "COMMISSION",
                           "COTISATION", "FRAIS BANCAIRE", "INTERET", "ECHEANCE PRET",
                           "BANQUE POSTALE", "BNP", "SOCIETE GENERALE", "CAISSE D EPARGNE",
                           "CREDIT AGRICOLE", "LCL", "BOURSORAMA", "HELLO BANK",
                           "REVOLUT", "N26", "QONTO", "SHINE", "COMPTE", "CARTE BANCAIRE"],
    "Transferts d'argent": ["SENDWAVE", "WESTERN UNION", "MONEYGRAM", "WISE", "REMITLY",
                             "TAPTAP SEND", "RIA ", "ORANGE MONEY", "WAVE ", "MONEY TRANSFER",
                             "TRANSFERT"],
    "Commerces de proximité": ["SUMUP", "ZETTLE", "IZETTLE", "TRESOR FRUITS", "TABAC",
                                "PRESSE", "COIFF", "PRESSING", "FLEURISTE", "MARCHE"],
    "Retraits d'espèces": ["RETRAIT", "DAB", "DISTRIBUTEUR", "ATM"],
    "Impôts et taxes": ["DGFIP", "IMPOT", "TRESOR PUBLIC", "TAXE", "URSSAF", "TVA",
                         "FONCIERE", "HABITATION", "CFE"],

    # Sorties — entreprise
    "Salaires versés": ["SALAIRE VERSE", "VIREMENT SALAIRE", "PAIE ", "NET A PAYER"],
    "Charges sociales": ["URSSAF", "RETRAITE COMPL", "MUTUELLE ENTREPRISE", "PREVOYANCE",
                          "AGIRC", "ARRCO", "CIPAV", "SSI "],
    "Fournisseurs": ["FOURNISSEUR", "FACTURE FRS", "ACHAT MARCHANDISE", "SUPPLIER"],
}

CATEGORIE_DEFAUT_ENTREE = "Autres encaissements"
CATEGORIE_DEFAUT_SORTIE = "Autres dépenses"


# Categories reservees aux entrees d'argent
_CATEGORIES_ENTREE = {"Salaires et revenus", "Encaissements clients",
                      "Aides et allocations"}


def categoriser(libelle: str, montant) -> str:
    """
    Range une operation dans une categorie parlante.

    Le sens de l'operation prime : un achat chez un commercant equipe SumUp
    n'est pas un encaissement client, meme si « SUMUP » apparait dans le libelle.
    """
    t = _sans_accent(libelle)
    entree = float(montant) > 0
    for categorie, mots in CATEGORIES.items():
        if entree != (categorie in _CATEGORIES_ENTREE):
            continue                      # categorie du mauvais sens
        for mot in mots:
            if mot in t:
                return categorie
    return CATEGORIE_DEFAUT_ENTREE if entree else CATEGORIE_DEFAUT_SORTIE


# ---------------------------------------------------------------------------
# Nettoyage des libelles pour affichage
# ---------------------------------------------------------------------------

# Une charge fixe se reconnait a sa nature, pas seulement a sa repetition :
# sur un mois de releve, une mensualite n'apparait qu'une fois.
_RE_CHARGE_FIXE = re.compile(
    r"\b(PRELEVEMENT|PRLV|ABONNEMENT|LOYER|MENSUALITE|ECHEANCE|COTISATION|"
    r"CREDIT|PRET|ASSURANCE|MUTUELLE|FORFAIT|SOUSCRIPTION|SUBSCRIPTION)\b",
    re.IGNORECASE)


# Un paiement par carte ou un retrait n'est jamais une charge fixe, meme
# repete a l'identique : l'utilisateur peut cesser d'y aller demain.
_RE_JAMAIS_FIXE = re.compile(
    r"\b(ACHAT|CARTE|CB|RETRAIT|DAB|DISTRIBUTEUR|ESPECES|PAIEMENT CB)\b",
    re.IGNORECASE)


def _est_une_charge_fixe(libelle: str, montants: list[float]) -> bool:
    """
    Vrai si l'operation ressemble a une echeance reguliere.

    Une charge fixe est subie : on ne peut pas l'arreter du jour au lendemain.
    Un achat par carte, meme repete au centime pres, reste une depense
    sur laquelle l'utilisateur garde la main.
    """
    if _RE_JAMAIS_FIXE.search(libelle):
        return False
    if _RE_CHARGE_FIXE.search(libelle):
        return True
    if len(montants) < 2:
        return False
    moyenne = sum(montants) / len(montants)
    if moyenne <= 0:
        return False
    return (max(montants) - min(montants)) / moyenne < 0.12


_BRUIT = re.compile(
    r"\b(ACHAT CB|ACHAT|CARTE X?\d*|CARTE|PRELEVEMENT DE|PRELEVEMENT|"
    r"PRLV SEPA|PRLV|VIREMENT DE|VIREMENT|VIR SEPA|VIR|RETRAIT|PAIEMENT|CB|"
    r"SEPA|REF\s*:?\s*\w*|MANDAT\s*\w*|DU\s+\d{2}[./-]\d{2})\b",
    re.IGNORECASE)

# Dates collees au libelle : « CARREFOUR 15.05.26 », « FNAC 03/11 »
_RE_DATE_DANS_LIBELLE = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")


def nom_lisible(libelle: str) -> str:
    """« ACHAT CB CARREFOUR 28.05.26 » devient « Carrefour »."""
    t = _BRUIT.sub(" ", libelle)
    t = _RE_DATE_DANS_LIBELLE.sub(" ", t)             # dates collees
    t = re.sub(r"\b\d{4,}\b", " ", t)                 # numeros longs
    t = re.sub(r"[*/\\|]", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" .-:")
    if not t:
        t = libelle.strip()
    # Capitalisation douce : CARREFOUR -> Carrefour, mais on garde les sigles
    mots = []
    for m in t.split():
        mots.append(m if (len(m) <= 3 and m.isupper()) else m.capitalize())
    return " ".join(mots)[:42]


# ---------------------------------------------------------------------------
# Postes de depense et de recette
# ---------------------------------------------------------------------------

def _texte(cle: str, **variables) -> str:
    """
    Repli quand l'interface ne fournit pas sa propre traduction.

    Ce module reste pur : il ne connait ni Streamlit ni la langue de
    lecture. L'appelant la lui donne ; sans cela, il repond en francais.
    """
    from langues import traduire
    return traduire(cle, "fr", **variables)


def _nombre(valeur, code: str = "fr") -> str:
    from langues import formater_nombre
    return formater_nombre(valeur, 0, code)


@dataclass
class Poste:
    """Un regroupement d'operations, presente en langage clair."""
    nom: str
    categorie: str
    total: Decimal
    nombre: int
    moyenne: Decimal
    par_mois: Decimal
    fixe: bool                      # montant stable = echeance fixe
    jour_habituel: int | None = None
    dates: list[date] = field(default_factory=list)

    @property
    def est_une_entree(self) -> bool:
        return self.total > 0

    def phrase(self, t=None, nombre=None, symbole: str = "€") -> str:
        """
        Une phrase qu'un utilisateur comprend sans explication.

        `t` traduit, `nombre` met en forme selon la langue de lecture.
        Les deux sont injectes : ce module ne connait pas l'interface.
        """
        t = t or _texte
        nombre = nombre or _nombre
        somme = nombre(abs(float(self.par_mois)))

        if self.fixe and self.jour_habituel:
            sens = t("an.recu") if self.est_une_entree else t("an.preleve")
            return t("an.fixe_mensuel", somme=somme, sym=symbole,
                     sens=sens, jour=self.jour_habituel)
        if self.nombre == 1:
            return t("an.unique")
        return t("an.environ", somme=somme, sym=symbole, n=self.nombre)


def _jour_habituel(dates: list[date]) -> int | None:
    """Renvoie le jour du mois si les operations tombent toujours au meme moment."""
    if len(dates) < 2:
        return None
    jours = [d.day for d in dates]
    moyen = round(sum(jours) / len(jours))
    if all(abs(j - moyen) <= 3 for j in jours):
        return moyen
    return None


def construire_postes(mouvements, nb_mois: float) -> list[Poste]:
    """Regroupe les operations par beneficiaire et calcule un budget mensuel."""
    groupes: dict[str, list] = defaultdict(list)
    for m in mouvements:
        cle = nom_lisible(m.libelle).upper()[:24]
        groupes[cle].append(m)

    postes: list[Poste] = []
    for _, lignes in groupes.items():
        total = sum((Decimal(str(l.montant)) for l in lignes), Decimal("0"))
        montants = [abs(float(l.montant)) for l in lignes]
        moyenne = sum(montants) / len(montants)
        # Un montant est « fixe » si l'ecart entre les operations est faible
        fixe = _est_une_charge_fixe(lignes[-1].libelle, montants)
        dates = sorted(l.jour for l in lignes)

        postes.append(Poste(
            nom=nom_lisible(lignes[-1].libelle),
            categorie=categoriser(lignes[-1].libelle, total),
            total=_arr(total),
            nombre=len(lignes),
            moyenne=_arr(moyenne),
            par_mois=_arr(float(total) / max(nb_mois, 0.5)),
            fixe=fixe,
            jour_habituel=_jour_habituel(dates) if fixe else None,
            dates=dates,
        ))
    return sorted(postes, key=lambda p: abs(float(p.total)), reverse=True)


# ---------------------------------------------------------------------------
# Synthese globale
# ---------------------------------------------------------------------------

@dataclass
class Synthese:
    debut: date
    fin: date
    nb_mois: float
    nb_operations: int
    entrees: Decimal
    sorties: Decimal
    solde_periode: Decimal
    entrees_par_mois: Decimal
    sorties_par_mois: Decimal
    reste_par_mois: Decimal
    charges_fixes: Decimal          # par mois
    depenses_variables: Decimal     # par mois
    postes: list[Poste]
    par_categorie: dict[str, Decimal]

    @property
    def taux_epargne(self) -> float:
        if self.entrees_par_mois <= 0:
            return 0.0
        return float(self.reste_par_mois / self.entrees_par_mois * 100)

    @property
    def part_fixe(self) -> float:
        """Part des charges fixes dans les revenus — au-dela de 70 %, c'est tendu."""
        if self.entrees_par_mois <= 0:
            return 0.0
        return float(abs(self.charges_fixes) / self.entrees_par_mois * 100)

    @staticmethod
    def _somme(v) -> str:
        """Repli francais. L'interface passe son propre formateur."""
        return _nombre(abs(float(v)))

    def messages(self, t=None, nombre=None,
                 symbole: str = "€") -> list[tuple[str, str]]:
        """Constats en langage clair. Renvoie (niveau, texte)."""
        t = t or _texte
        somme = nombre or self._somme

        out: list[tuple[str, str]] = []
        e = float(self.entrees_par_mois)
        r = float(self.reste_par_mois)
        pct = f"{self.taux_epargne:.0f}"

        if r < 0:
            out.append(("alerte", t("an.deficit", somme=somme(abs(r)),
                                    sym=symbole)))
        elif e > 0 and r / e < 0.05:
            out.append(("attention", t("an.marge_faible", somme=somme(abs(r)),
                                       sym=symbole, p=pct)))
        else:
            out.append(("bon", t("an.epargne", somme=somme(abs(r)),
                                 sym=symbole, p=pct)))

        if self.part_fixe > 70:
            out.append(("attention", t("an.charges_lourdes",
                                       p=f"{self.part_fixe:.0f}")))

        if self.postes:
            sorties = [p for p in self.postes if not p.est_une_entree]
            if sorties:
                p = sorties[0]
                out.append(("info", t("an.premier_poste", nom=p.nom,
                                      somme=somme(abs(float(p.par_mois))),
                                      sym=symbole)))

        variables = float(abs(self.depenses_variables))
        if e > 0 and variables / e > 0.35:
            out.append(("info", t("an.variables", somme=somme(variables),
                                  sym=symbole)))
        return out


def analyser_lisible(mouvements) -> Synthese:
    """Produit une lecture comprehensible d'une liste de mouvements."""
    if not mouvements:
        raise ValueError("Aucun mouvement à analyser.")

    debut = min(m.jour for m in mouvements)
    fin = max(m.jour for m in mouvements)
    nb_jours = max((fin - debut).days, 1)
    nb_mois = max(nb_jours / 30.44, 0.5)

    entrees = sum((Decimal(str(m.montant)) for m in mouvements if m.montant > 0), Decimal("0"))
    sorties = sum((Decimal(str(m.montant)) for m in mouvements if m.montant < 0), Decimal("0"))

    postes = construire_postes(mouvements, nb_mois)
    fixes = sum((p.par_mois for p in postes if p.fixe and not p.est_une_entree), Decimal("0"))
    variables = sum((p.par_mois for p in postes if not p.fixe and not p.est_une_entree),
                    Decimal("0"))

    par_categorie: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for m in mouvements:
        par_categorie[categoriser(m.libelle, m.montant)] += Decimal(str(m.montant))

    return Synthese(
        debut=debut, fin=fin, nb_mois=round(nb_mois, 1),
        nb_operations=len(mouvements),
        entrees=_arr(entrees), sorties=_arr(sorties),
        solde_periode=_arr(entrees + sorties),
        entrees_par_mois=_arr(float(entrees) / nb_mois),
        sorties_par_mois=_arr(float(sorties) / nb_mois),
        reste_par_mois=_arr(float(entrees + sorties) / nb_mois),
        charges_fixes=_arr(fixes),
        depenses_variables=_arr(variables),
        postes=postes,
        par_categorie={k: _arr(v) for k, v in
                       sorted(par_categorie.items(), key=lambda x: abs(float(x[1])),
                              reverse=True)},
    )
