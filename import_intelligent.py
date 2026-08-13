"""
IMPORT INTELLIGENT DE RELEVES
PrevuFlow — SMD Global Consulting LLC

Lit n'importe quel releve bancaire ou tableur, reconnait tout seul les colonnes,
puis deduit les operations recurrentes a projeter dans le futur.

Aucun parametrage demande a l'utilisateur : il depose son fichier, c'est tout.

Dependances : pandas · openpyxl (.xlsx) · pdfplumber (.pdf)
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import pandas as pd

from moteur_tresorerie import Operation, Recurrence


# ---------------------------------------------------------------------------
# Reconnaissance des colonnes
# ---------------------------------------------------------------------------

def _normaliser(texte: str) -> str:
    """Retire accents, majuscules et ponctuation pour comparer des intitules."""
    t = unicodedata.normalize("NFKD", str(texte))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t.lower())


# Intitules rencontres dans les releves francais, anglais et exports comptables
MOTS_DATE = ["date", "dateoperation", "datevaleur", "datecomptable", "jour",
             "transactiondate", "postingdate", "valuedate", "datedoperation"]
MOTS_LIBELLE = ["libelle", "libelledoperation", "description", "intitule", "objet",
                "nature", "detail", "operation", "narrative", "memo", "payee",
                "beneficiaire", "tiers", "reference"]
MOTS_MONTANT = ["montant", "amount", "valeur", "somme", "mouvement", "solde mouvement"]
MOTS_DEBIT = ["debit", "depense", "sortie", "retrait", "withdrawal", "paidout"]
MOTS_CREDIT = ["credit", "recette", "entree", "depot", "deposit", "paidin", "encaissement"]


def _trouver(colonnes: list[str], candidats: list[str]) -> str | None:
    """Cherche d'abord une correspondance exacte, puis partielle."""
    normalisees = {c: _normaliser(c) for c in colonnes}
    for col, norm in normalisees.items():
        if norm in [_normaliser(c) for c in candidats]:
            return col
    for col, norm in normalisees.items():
        for cand in candidats:
            n = _normaliser(cand)
            if len(n) >= 4 and (n in norm or norm in n):
                return col
    return None


@dataclass
class Colonnes:
    date: str | None = None
    libelle: str | None = None
    montant: str | None = None
    debit: str | None = None
    credit: str | None = None

    @property
    def exploitable(self) -> bool:
        return bool(self.date and (self.montant or (self.debit or self.credit)))

    def resume(self) -> str:
        if self.montant:
            m = f"montant = « {self.montant} »"
        else:
            m = f"débit = « {self.debit} », crédit = « {self.credit} »"
        return f"date = « {self.date} », libellé = « {self.libelle} », {m}"


def detecter_colonnes(df: pd.DataFrame) -> Colonnes:
    """Devine le role de chaque colonne, sans rien demander a l'utilisateur."""
    cols = list(df.columns)
    c = Colonnes(
        date=_trouver(cols, MOTS_DATE),
        libelle=_trouver(cols, MOTS_LIBELLE),
        montant=_trouver(cols, MOTS_MONTANT),
        debit=_trouver(cols, MOTS_DEBIT),
        credit=_trouver(cols, MOTS_CREDIT),
    )

    # Repli : chercher par le contenu plutot que par l'intitule
    if not c.date:
        for col in cols:
            try:
                converti = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
                if converti.notna().mean() > 0.8:
                    c.date = col
                    break
            except Exception:
                continue

    if not (c.montant or c.debit or c.credit):
        for col in cols:
            if col in (c.date, c.libelle):
                continue
            serie = _vers_nombre(df[col])
            if serie.notna().mean() > 0.8:
                c.montant = col
                break

    if not c.libelle:
        restantes = [x for x in cols if x not in (c.date, c.montant, c.debit, c.credit)]
        if restantes:
            # La colonne texte la plus riche
            c.libelle = max(restantes,
                            key=lambda x: df[x].astype(str).str.len().mean())
    return c


def _vers_nombre(serie: pd.Series) -> pd.Series:
    """Convertit '1 234,56', '1,234.56', '(500)' ou '-500 EUR' en nombre."""
    def conv(v):
        if pd.isna(v):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        t = str(v).strip()
        negatif = t.startswith("(") and t.endswith(")")
        t = re.sub(r"[^\d,.\-]", "", t)
        if not t or t in "-.,":
            return None
        # Separateur decimal : le dernier symbole rencontre
        if "," in t and "." in t:
            t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".") if len(t.split(",")[-1]) <= 2 else t.replace(",", "")
        try:
            n = float(t)
            return -n if negatif else n
        except ValueError:
            return None
    return serie.map(conv)


# ---------------------------------------------------------------------------
# Lecture du fichier
# ---------------------------------------------------------------------------

def lire_fichier(chemin_ou_flux, nom: str = "") -> pd.DataFrame:
    """Lit un PDF, un CSV ou un Excel en devinant separateur et encodage."""
    nom = (nom or str(chemin_ou_flux)).lower()

    if nom.endswith(".pdf"):
        return lire_pdf(chemin_ou_flux)

    if nom.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(chemin_ou_flux)

    for encodage in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (";", ",", "\t", "|"):
            try:
                if hasattr(chemin_ou_flux, "seek"):
                    chemin_ou_flux.seek(0)
                df = pd.read_csv(chemin_ou_flux, sep=sep, encoding=encodage,
                                 engine="python", on_bad_lines="skip")
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue
    raise ValueError("Format de fichier non reconnu. "
                     "Formats acceptés : CSV, XLSX, XLS.")


# ---------------------------------------------------------------------------
# Lecture des releves PDF
# ---------------------------------------------------------------------------

MOIS_FR = {
    "janv": 1, "janvier": 1, "fevr": 2, "fev": 2, "février": 2, "fevrier": 2,
    "mars": 3, "avr": 4, "avril": 4, "mai": 5, "juin": 6,
    "juil": 7, "juillet": 7, "aout": 8, "août": 8, "sept": 9, "septembre": 9,
    "oct": 10, "octobre": 10, "nov": 11, "novembre": 11, "dec": 12,
    "déc": 12, "decembre": 12, "décembre": 12,
}

# 12/07/2026 · 12-07-26 · 12.07.2026
_RE_DATE_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b")
# 12 juil. 2026 · 3 mars
_RE_DATE_TXT = re.compile(
    r"\b(\d{1,2})\s+([a-zéûôA-ZÉÛÔ]{3,10})\.?\s*(\d{4})?\b")
# 1 234,56 · 1.234,56 · 1,234.56 · -87,90 · 87,90-
_RE_MONTANT = re.compile(
    r"(?<![\d,.])("
    r"-?\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+[.,]\d{2}-?"   # 1 234,56 / 1.234,56
    r"|-?\d+[.,]\d{2}-?"                                      # 2850,00 / 87,90
    r")(?![\d])")


def _date_depuis_ligne(ligne: str, annee_defaut: int) -> date | None:
    m = _RE_DATE_NUM.search(ligne)
    if m:
        j, mo, an = m.group(1), m.group(2), m.group(3)
        try:
            j, mo = int(j), int(mo)
            if not (1 <= j <= 31 and 1 <= mo <= 12):
                return None
            if an is None:
                annee = annee_defaut
            else:
                annee = int(an)
                if annee < 100:
                    annee += 2000
            return date(annee, mo, j)
        except ValueError:
            return None

    m = _RE_DATE_TXT.search(ligne)
    if m:
        j, nom_mois, an = m.group(1), m.group(2).lower().rstrip("."), m.group(3)
        mo = MOIS_FR.get(nom_mois) or MOIS_FR.get(nom_mois[:4]) or MOIS_FR.get(nom_mois[:3])
        if mo:
            try:
                return date(int(an) if an else annee_defaut, mo, int(j))
            except ValueError:
                return None
    return None


def _montants_depuis_ligne(ligne: str) -> list[float]:
    valeurs = []
    for brut in _RE_MONTANT.findall(ligne):
        t = brut.strip()
        negatif = t.startswith("-") or t.endswith("-")
        t = t.strip("-").replace(" ", "").replace(" ", "")
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") \
                else t.replace(",", "")
        elif "," in t:
            t = t.replace(",", ".")
        try:
            v = float(t)
            valeurs.append(-v if negatif else v)
        except ValueError:
            continue
    return valeurs


_RE_GROUPE_MILLIERS = re.compile(r"^\d{1,3}$")
_RE_FIN_MONTANT     = re.compile(r"^\d{3}[.,]\d{2}-?$")


def _recoller_milliers(mots: list[dict]) -> list[dict]:
    """
    Dans un PDF, « 2 850,00 » est souvent decoupe en deux mots : « 2 » et
    « 850,00 ». Sans recollage, le montant lu vaut 850 au lieu de 2850.

    On fusionne deux mots voisins lorsque le premier est un groupe de
    milliers, le second la fin d'un montant, et qu'ils se touchent
    horizontalement.
    """
    if len(mots) < 2:
        return mots

    resultat: list[dict] = []
    i = 0
    while i < len(mots):
        courant = mots[i]
        fusionne = False
        if i + 1 < len(mots):
            suivant = mots[i + 1]
            ecart = suivant["x0"] - courant["x1"]
            if (_RE_GROUPE_MILLIERS.match(courant["text"])
                    and _RE_FIN_MONTANT.match(suivant["text"])
                    and 0 <= ecart <= 6):
                courant = {**suivant,
                           "text": courant["text"] + suivant["text"],
                           "x0": courant["x0"]}
                i += 1
                fusionne = True
        resultat.append(courant)
        i += 1
        if fusionne:
            continue
    return resultat


# Une date collee : 28.05.26 · 5/6/26 · 28-05-2026
_RE_EST_UNE_DATE = re.compile(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$")
# Un montant isole : 14,00 · 1 234,56 · 1.234,56 · -87,90
_RE_EST_UN_MONTANT = re.compile(
    r"^-?\d{1,3}(?:[\s\u00a0\u202f.,]\d{3})+[.,]\d{2}-?$"   # 1 234,56
    r"|^-?\d+[.,]\d{2}-?$")                                     # 1234,56 · 14,00


def _est_un_montant(texte: str) -> bool:
    """Distingue un montant d'une date : « 28.05.26 » n'est pas 28,05 euros."""
    t = texte.strip()
    if _RE_EST_UNE_DATE.match(t):
        return False
    return bool(_RE_EST_UN_MONTANT.match(t))


def _choisir_colonnes(positions: list[float]) -> tuple[float | None, float | None]:
    """
    Deduit les colonnes debit et credit a partir des positions observees.

    On ecarte les groupes marginaux (moins de 3 % des montants), puis on retient
    les deux groupes les plus a droite : dans un releve, les montants sont
    toujours alignes a droite, le libelle occupant la gauche.
    """
    groupes = _regrouper_positions(positions)
    if len(groupes) < 2:
        return (None, None)

    seuil = max(2, len(positions) * 0.03)
    peuples = [g for g in groupes
               if sum(1 for p in positions if abs(p - g) <= 9) >= seuil]
    if len(peuples) < 2:
        return (None, None)

    deux_a_droite = sorted(peuples)[-2:]
    return (deux_a_droite[0], deux_a_droite[1])


def _regrouper_positions(valeurs: list[float], tolerance: float = 9.0) -> list[float]:
    """Regroupe des positions proches et renvoie le centre de chaque groupe."""
    if not valeurs:
        return []
    valeurs = sorted(valeurs)
    groupes, courant = [], [valeurs[0]]
    for v in valeurs[1:]:
        if v - courant[-1] <= tolerance:
            courant.append(v)
        else:
            groupes.append(courant)
            courant = [v]
    groupes.append(courant)
    return [sum(g) / len(g) for g in groupes]


# Lignes a ignorer : ce ne sont pas des operations
_LIGNES_EXCLUES = re.compile(
    r"(ancien\s+solde|nouveau\s+solde|solde\s+(?:au|cr|dØbiteur|crØditeur|precedent|préc)"
    r"|total\s+des|report|frais\s+et\s+cotisations|situation\s+de\s+vos)",
    re.IGNORECASE)


def _nettoyer_libelle(texte: str) -> str:
    """Retire les caracteres non decodes par le PDF et les dates."""
    texte = re.sub(r"\(cid:\d+\)", " ", texte)     # glyphes non mappes
    texte = _RE_DATE_NUM.sub(" ", texte)
    texte = _RE_DATE_TXT.sub(" ", texte)
    texte = re.sub(r"[<>|]", " ", texte)
    return re.sub(r"\s{2,}", " ", texte).strip(" .-*:")


def lire_pdf(chemin_ou_flux) -> pd.DataFrame:
    """
    Extrait les operations d'un releve bancaire PDF.

    Les colonnes debit / credit ne sont pas devinees d'apres des en-tetes
    (beaucoup de banques n'en impriment pas) mais deduites de la position
    horizontale reelle des montants dans le document.

    Un PDF scanne - une simple image - est rejete avec un message explicite
    plutot que de renvoyer un resultat faux.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ValueError(
            "La lecture des PDF nécessite pdfplumber. "
            "Installez-le avec : pip install pdfplumber")

    lignes_utiles: list[list[dict]] = []
    tout_le_texte: list[str] = []

    with pdfplumber.open(chemin_ou_flux) as pdf:
        for page in pdf.pages:
            mots = page.extract_words(use_text_flow=False)
            if not mots:
                continue
            tout_le_texte.append(page.extract_text() or "")
            groupes: dict[int, list[dict]] = {}
            for m in mots:
                groupes.setdefault(round(m["top"] / 3), []).append(m)
            for _, mots_ligne in sorted(groupes.items()):
                lignes_utiles.append(
                    _recoller_milliers(sorted(mots_ligne, key=lambda w: w["x0"])))

    if not lignes_utiles:
        raise ValueError(
            "Ce PDF ne contient aucun texte : c'est probablement un document "
            "scanné. Exportez plutôt votre relevé au format CSV ou Excel "
            "depuis votre banque.")

    annees = [int(a) for a in re.findall(r"\b(20\d{2})\b", " ".join(tout_le_texte))]
    annee_defaut = max(set(annees), key=annees.count) if annees else date.today().year

    # --- Decoupage en comptes -----------------------------------------------
    # Un releve peut contenir plusieurs comptes (courant, livret...). Chaque
    # compte est delimite par une ligne « Ancien solde ». On ne retient que le
    # compte le plus fourni : melanger les comptes fausserait la tresorerie.
    _RE_DEBUT_COMPTE = re.compile(r"ancien\s+solde", re.IGNORECASE)
    sections: list[list[list[dict]]] = [[]]
    for mots_ligne in lignes_utiles:
        texte_ligne = " ".join(m["text"] for m in mots_ligne)
        if _RE_DEBUT_COMPTE.search(texte_ligne) and sections[-1]:
            sections.append([])
        sections[-1].append(mots_ligne)

    def _nb_operations(section):
        n = 0
        for ml in section:
            t = " ".join(m["text"] for m in ml)
            if _date_depuis_ligne(t, annee_defaut) and any(
                    _est_un_montant(m["text"]) for m in ml):
                n += 1
        return n

    if len(sections) > 1:
        lignes_utiles = max(sections, key=_nb_operations)

    # --- 1re passe : reperer les lignes d'operation et les positions des montants
    candidates = []
    positions = []
    for mots_ligne in lignes_utiles:
        ligne = " ".join(m["text"] for m in mots_ligne).strip()
        if len(ligne) < 10 or _LIGNES_EXCLUES.search(ligne):
            continue
        jour = _date_depuis_ligne(ligne, annee_defaut)
        if not jour:
            continue
        montants = []
        for m in mots_ligne:
            if not _est_un_montant(m["text"]):
                continue
            valeurs = _montants_depuis_ligne(m["text"])
            if valeurs:
                montants.append((m, valeurs[0]))
        if not montants:
            continue
        candidates.append((jour, mots_ligne, montants))
        positions.extend(m["x1"] for m, _ in montants)

    if not candidates:
        raise ValueError(
            "Aucune opération n'a pu être extraite de ce PDF. "
            "La mise en page n'est pas reconnue — exportez votre relevé "
            "en CSV ou Excel depuis votre banque.")

    # --- Deduction des colonnes depuis les positions observees ---------------
    x_debit, x_credit = _choisir_colonnes(positions)

    # --- 2e passe : construction des operations ------------------------------
    operations = []
    for jour, mots_ligne, montants in candidates:
        if x_debit is not None:
            debits  = [v for m, v in montants if abs(m["x1"] - x_debit) <= 9]
            credits = [v for m, v in montants if abs(m["x1"] - x_credit) <= 9]
            if credits:
                montant = abs(credits[0])
            elif debits:
                montant = -abs(debits[0])
            else:
                continue
        else:
            montant = montants[0][1]

        ligne = " ".join(m["text"] for m in mots_ligne)
        for m, _ in montants:
            ligne = ligne.replace(m["text"], " ")
        libelle = _nettoyer_libelle(ligne)
        if len(libelle) < 3:
            continue

        operations.append({
            "Date": jour.strftime("%d/%m/%Y"),
            "Libelle": libelle[:80],
            "Montant": montant,
        })

    if not operations:
        raise ValueError(
            "Aucune opération exploitable dans ce PDF. "
            "Exportez votre relevé en CSV ou Excel depuis votre banque.")

    return pd.DataFrame(operations)


@dataclass
class Mouvement:
    """Une ligne du releve, une fois nettoyee."""
    jour: date
    libelle: str
    montant: Decimal


def extraire_mouvements(df: pd.DataFrame, colonnes: Colonnes | None = None) -> list[Mouvement]:
    """Transforme un tableau brut en liste de mouvements exploitables."""
    c = colonnes or detecter_colonnes(df)
    if not c.exploitable:
        raise ValueError(
            "Impossible d'identifier les colonnes. "
            f"Colonnes trouvées : {', '.join(map(str, df.columns))}")

    dates = pd.to_datetime(df[c.date], errors="coerce", dayfirst=True)

    if c.montant:
        montants = _vers_nombre(df[c.montant])
    else:
        debit = _vers_nombre(df[c.debit]).fillna(0) if c.debit else 0
        credit = _vers_nombre(df[c.credit]).fillna(0) if c.credit else 0
        # Les debits sont souvent notes en positif dans une colonne dediee
        montants = credit - abs(debit)

    libelles = df[c.libelle].astype(str) if c.libelle else pd.Series([""] * len(df))

    mouvements = []
    for d, lib, m in zip(dates, libelles, montants):
        if pd.isna(d) or m is None or pd.isna(m) or float(m) == 0:
            continue
        mouvements.append(Mouvement(
            jour=d.date(),
            libelle=str(lib).strip()[:80],
            montant=Decimal(str(round(float(m), 2))),
        ))
    return sorted(mouvements, key=lambda x: x.jour)


# ---------------------------------------------------------------------------
# Detection des recurrences
# ---------------------------------------------------------------------------

def _cle_regroupement(libelle: str) -> str:
    """Regroupe 'CB CARREFOUR 12/07' et 'CB CARREFOUR 19/07' sous la meme cle."""
    t = _normaliser(libelle)
    t = re.sub(r"\d+", "", t)          # retire dates, numeros de carte, references
    return t[:22]


@dataclass
class Recurrent:
    libelle: str
    montant: Decimal
    recurrence: Recurrence
    prochaine_date: date
    occurrences: int
    regularite: float                 # 0 a 1 : plus c'est haut, plus c'est fiable

    @property
    def fiable(self) -> bool:
        return self.occurrences >= 3 and self.regularite >= 0.75


def detecter_recurrences(mouvements: list[Mouvement],
                         min_occurrences: int = 3) -> list[Recurrent]:
    """
    Repere les operations qui reviennent : loyer, salaire, abonnements, credits.

    Principe : regrouper par libelle nettoye, mesurer l'ecart entre les dates,
    et verifier que cet ecart est stable.
    """
    groupes: dict[str, list[Mouvement]] = defaultdict(list)
    for m in mouvements:
        groupes[_cle_regroupement(m.libelle)].append(m)

    resultats: list[Recurrent] = []

    for _, lignes in groupes.items():
        if len(lignes) < min_occurrences:
            continue
        lignes.sort(key=lambda x: x.jour)
        ecarts = [(lignes[i + 1].jour - lignes[i].jour).days
                  for i in range(len(lignes) - 1)]
        if not ecarts:
            continue

        ecart_type = median(ecarts)
        if ecart_type <= 0:
            continue

        # Regularite : proportion d'ecarts proches de la mediane (tolerance 25 %)
        tolerance = max(2, ecart_type * 0.25)
        reguliers = sum(1 for e in ecarts if abs(e - ecart_type) <= tolerance)
        regularite = reguliers / len(ecarts)
        if regularite < 0.6:
            continue

        if   ecart_type <= 2:   freq = Recurrence.QUOTIDIENNE
        elif ecart_type <= 9:   freq = Recurrence.HEBDOMADAIRE
        elif ecart_type <= 18:  freq = Recurrence.BIMENSUELLE
        elif ecart_type <= 45:  freq = Recurrence.MENSUELLE
        elif ecart_type <= 135: freq = Recurrence.TRIMESTRIELLE
        elif ecart_type <= 400: freq = Recurrence.ANNUELLE
        else:                   continue

        montant_moyen = Decimal(str(round(
            float(sum(l.montant for l in lignes)) / len(lignes), 2)))

        resultats.append(Recurrent(
            libelle=lignes[-1].libelle,
            montant=montant_moyen,
            recurrence=freq,
            prochaine_date=lignes[-1].jour + timedelta(days=int(ecart_type)),
            occurrences=len(lignes),
            regularite=round(regularite, 2),
        ))

    return sorted(resultats, key=lambda r: abs(float(r.montant)), reverse=True)


def vers_operations(recurrents: list[Recurrent],
                    seulement_fiables: bool = True) -> list[Operation]:
    """Convertit les recurrences detectees en operations prêtes a projeter."""
    return [
        Operation(
            libelle=r.libelle,
            montant=r.montant,
            date_operation=r.prochaine_date,
            recurrence=r.recurrence,
            certaine=r.fiable,
            categorie="détecté automatiquement",
        )
        for r in recurrents
        if r.fiable or not seulement_fiables
    ]


# ---------------------------------------------------------------------------
# Chaine complete
# ---------------------------------------------------------------------------

def analyser(chemin_ou_flux, nom: str = "") -> dict:
    """
    Du fichier brut aux operations projetables, en un appel.

    Renvoie : colonnes reconnues, mouvements, recurrences, operations, solde final.
    """
    df = lire_fichier(chemin_ou_flux, nom)
    colonnes = detecter_colonnes(df)
    mouvements = extraire_mouvements(df, colonnes)
    recurrences = detecter_recurrences(mouvements)
    return {
        "colonnes": colonnes,
        "lignes_lues": len(df),
        "mouvements": mouvements,
        "periode": (mouvements[0].jour, mouvements[-1].jour) if mouvements else None,
        "recurrences": recurrences,
        "operations": vers_operations(recurrences),
        "total_entrees": sum((m.montant for m in mouvements if m.montant > 0), Decimal("0")),
        "total_sorties": sum((m.montant for m in mouvements if m.montant < 0), Decimal("0")),
    }
