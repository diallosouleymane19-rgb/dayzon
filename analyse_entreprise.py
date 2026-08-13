"""
INDICATEURS FINANCIERS D'ENTREPRISE
PrevuFlow — SMD Global Consulting LLC

Analyse financiere pure. Aucun plan comptable, aucun referentiel national.

Le principe : une entreprise, ou qu'elle soit dans le monde, possede toujours
deux choses — des flux bancaires et des factures. C'est tout ce dont ce module
a besoin. Il n'a jamais besoin d'une comptabilite.

Les indicateurs produits sont ceux qu'un dirigeant ou un investisseur regarde,
et ils portent les memes noms a Dakar, Istanbul, Londres ou Austin :
runway, burn rate, DSO, DPO, point mort, concentration client.
"""

from __future__ import annotations

import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd


def _texte(cle: str, **variables) -> str:
    """
    Repli quand l'interface ne fournit pas sa propre traduction.

    Ce module reste pur : il ne connait ni Streamlit ni la langue de
    lecture. L'appelant la lui donne ; sans cela, il repond en francais.
    """
    from langues import traduire
    return traduire(cle, "fr", **variables)


def _sans_accent(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _d(v) -> Decimal:
    """Conversion tolerante vers Decimal. Renvoie 0 si illisible."""
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    t = str(v).strip()
    if not t:
        return Decimal("0")
    negatif = t.startswith("(") and t.endswith(")")     # (1 234,56) = negatif
    t = t.strip("()")
    t = re.sub(r"[^\d,.\-]", "", t)
    if "," in t and "." in t:
        # le dernier separateur rencontre est le decimal
        t = (t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".")
             else t.replace(",", ""))
    elif "," in t:
        t = t.replace(",", ".")
    try:
        v = Decimal(t)
    except Exception:
        return Decimal("0")
    return -v if negatif else v


def _arr(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ===========================================================================
# LES FACTURES
# ===========================================================================

@dataclass
class Facture:
    """
    Une facture emise ou recue. Le seul document dont l'analyse a besoin.
    Volontairement depouille : ni TVA, ni compte, ni journal.
    """
    date_emission: date
    tiers: str
    montant: Decimal
    sens: str = "client"                    # "client" (a encaisser) ou "fournisseur"
    devise: str = "EUR"
    echeance: date | None = None
    date_paiement: date | None = None

    @property
    def payee(self) -> bool:
        return self.date_paiement is not None

    @property
    def delai_reglement(self) -> int | None:
        """Nombre de jours reellement ecoules entre l'emission et le paiement."""
        if self.date_paiement is None:
            return None
        return (self.date_paiement - self.date_emission).days

    def jours_de_retard(self, au: date | None = None) -> int:
        """Jours de retard sur l'echeance. 0 si payee a temps ou pas encore due."""
        if self.echeance is None:
            return 0
        fin = self.date_paiement or (au or date.today())
        return max(0, (fin - self.echeance).days)

    def est_en_retard(self, au: date | None = None) -> bool:
        """
        Prend la date d'arrete en argument : juger un retard depend du jour
        auquel on se place, jamais du jour ou le calcul est lance.
        """
        return not self.payee and self.jours_de_retard(au) > 0

    @property
    def en_retard(self) -> bool:
        """Retard constate aujourd'hui."""
        return self.est_en_retard()


# --- Reconnaissance des colonnes -------------------------------------------

_MOTS = {
    "date_emission": ["DATE EMISSION", "DATE FACTURE", "DATE DE FACTURE", "INVOICE DATE",
                      "ISSUE DATE", "DATE D EMISSION", "EMISSION", "DATE", "FECHA"],
    "tiers":         ["CLIENT", "CUSTOMER", "FOURNISSEUR", "SUPPLIER", "VENDOR",
                      "TIERS", "NOM", "NAME", "COMPANY", "SOCIETE", "RAISON SOCIALE",
                      "PARTNER", "COMPTE", "ACCOUNT"],
    "montant":       ["MONTANT TTC", "TOTAL TTC", "MONTANT", "TOTAL", "AMOUNT",
                      "TOTAL AMOUNT", "GRAND TOTAL", "VALEUR", "IMPORTE", "TTC"],
    "echeance":      ["ECHEANCE", "DATE ECHEANCE", "DATE D ECHEANCE", "DUE DATE",
                      "DATE LIMITE", "PAYMENT DUE", "VENCIMIENTO"],
    "date_paiement": ["DATE PAIEMENT", "DATE DE PAIEMENT", "DATE REGLEMENT",
                      "PAYMENT DATE", "DATE PAYE", "PAID DATE", "PAID ON",
                      "DATE ENCAISSEMENT", "REGLE LE"],
    "devise":        ["DEVISE", "CURRENCY", "MONNAIE", "CUR", "CCY"],
    "statut":        ["STATUT", "STATUS", "ETAT", "ETAT FACTURE", "PAYE", "PAID"],
}

# Un statut qui vaut paiement, quelle que soit la langue du logiciel
_STATUTS_PAYES = {"PAYE", "PAYEE", "PAID", "REGLE", "REGLEE", "SETTLED", "CLOSED",
                  "SOLDE", "SOLDEE", "ENCAISSE", "ENCAISSEE", "OUI", "YES", "1",
                  "TRUE", "COMPLETE", "COMPLETED", "PAGADO"}


def _trouver_colonne(colonnes: list[str], cible: str) -> str | None:
    """
    Rapproche un nom de colonne d'un role. On teste d'abord l'egalite exacte,
    puis l'inclusion : « Date de facture » doit primer sur « Date ».
    """
    propres = {c: _sans_accent(c).replace("_", " ").replace("-", " ").strip()
               for c in colonnes}
    mots = _MOTS[cible]
    for mot in mots:                              # egalite d'abord
        for brut, propre in propres.items():
            if propre == mot:
                return brut
    for mot in mots:                              # puis inclusion
        for brut, propre in propres.items():
            if mot in propre:
                return brut
    return None


def _vers_date(v) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip()
    if not t or t.upper() in {"NAT", "NAN", "NONE", "-"}:
        return None
    try:
        d = pd.to_datetime(t, dayfirst=True, errors="coerce")
        return None if pd.isna(d) else d.date()
    except Exception:
        return None


@dataclass
class LectureFactures:
    """Ce que la lecture d'un fichier a produit, et ce qu'elle n'a pas compris."""
    factures: list[Facture]
    colonnes_reconnues: dict[str, str]
    lignes_ignorees: int
    total: Decimal

    def resume(self) -> str:
        paires = [f"{role} → « {col} »" for role, col in self.colonnes_reconnues.items()]
        return " · ".join(paires) if paires else _texte("ent.aucune_colonne")


def lire_factures(fichier, nom_fichier: str = "", sens: str = "client",
                  devise_defaut: str = "EUR") -> LectureFactures:
    """
    Lit un fichier de factures exporte de n'importe quel outil de gestion,
    de facturation ou un simple tableau tenu a la main.

    Seules deux colonnes sont indispensables : une date et un montant.
    Tout le reste ameliore l'analyse sans etre obligatoire.
    """
    nom = (nom_fichier or getattr(fichier, "name", "")).lower()

    if nom.endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(fichier)
    else:
        donnees = fichier.read() if hasattr(fichier, "read") else fichier
        if isinstance(donnees, bytes):
            texte = None
            for encodage in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    texte = donnees.decode(encodage)
                    break
                except UnicodeDecodeError:
                    continue
            donnees = texte or donnees.decode("utf-8", errors="replace")
        # separateur devine : point-virgule frequent hors zone anglophone
        premiere = donnees.split("\n")[0]
        sep = ";" if premiere.count(";") > premiere.count(",") else ","
        df = pd.read_csv(io.StringIO(donnees), sep=sep)

    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    trouvees: dict[str, str] = {}
    for role in _MOTS:
        c = _trouver_colonne(cols, role)
        if c:
            trouvees[role] = c

    if "date_emission" not in trouvees or "montant" not in trouvees:
        manque = [r for r in ("date_emission", "montant") if r not in trouvees]
        raise ValueError(_texte(
            "ent.colonne_manquante",
            manque=" / ".join(_texte("ent.col_" + m) for m in manque),
            colonnes=", ".join(cols[:12])))

    factures: list[Facture] = []
    ignorees = 0

    for _, ligne in df.iterrows():
        jour = _vers_date(ligne.get(trouvees["date_emission"]))
        montant = _d(ligne.get(trouvees["montant"]))
        if jour is None or montant == 0:
            ignorees += 1
            continue

        paiement = (_vers_date(ligne.get(trouvees["date_paiement"]))
                    if "date_paiement" in trouvees else None)

        # Une colonne de statut peut declarer la facture payee sans donner de date
        if paiement is None and "statut" in trouvees:
            statut = _sans_accent(ligne.get(trouvees["statut"], "")).strip()
            if statut in _STATUTS_PAYES:
                paiement = _vers_date(ligne.get(trouvees.get("echeance", ""))) or jour

        tiers = str(ligne.get(trouvees["tiers"], "")).strip() if "tiers" in trouvees else ""
        devise = (str(ligne.get(trouvees["devise"], devise_defaut)).strip().upper()[:3]
                  if "devise" in trouvees else devise_defaut)

        factures.append(Facture(
            date_emission=jour,
            tiers=tiers or _texte("ent.non_identifie"),
            montant=abs(_arr(montant)),
            sens=sens,
            devise=devise or devise_defaut,
            echeance=(_vers_date(ligne.get(trouvees["echeance"]))
                      if "echeance" in trouvees else None),
            date_paiement=paiement,
        ))

    return LectureFactures(
        factures=factures,
        colonnes_reconnues=trouvees,
        lignes_ignorees=ignorees,
        total=_arr(sum((f.montant for f in factures), Decimal("0"))),
    )


# ===========================================================================
# LES INDICATEURS
# ===========================================================================

@dataclass
class Concentration:
    """La part de chaque client dans le chiffre d'affaires."""
    tiers: str
    montant: Decimal
    part: float


@dataclass
class IndicateursEntreprise:
    """
    Tous les nombres sont exprimes par mois pour rester comparables,
    quelle que soit la longueur de la periode importee.
    """
    debut: date
    fin: date
    nb_mois: float

    # Activite
    encaissements_par_mois: Decimal = Decimal("0")
    decaissements_par_mois: Decimal = Decimal("0")
    resultat_par_mois: Decimal = Decimal("0")
    croissance: float | None = None            # % d'un mois sur l'autre

    # Structure de couts
    charges_fixes: Decimal = Decimal("0")
    charges_variables: Decimal = Decimal("0")
    point_mort: Decimal | None = None          # CA mensuel pour equilibrer

    # Tresorerie
    tresorerie: Decimal = Decimal("0")
    burn_rate: Decimal = Decimal("0")          # perte mensuelle si negatif
    runway_mois: float | None = None           # mois avant epuisement

    # Clients
    ca_facture: Decimal = Decimal("0")
    encours_client: Decimal = Decimal("0")
    retard_client: Decimal = Decimal("0")
    dso: float | None = None                   # delai moyen d'encaissement
    taux_recouvrement: float | None = None
    concentration: list[Concentration] = field(default_factory=list)

    # Fournisseurs
    achats_factures: Decimal = Decimal("0")
    encours_fournisseur: Decimal = Decimal("0")
    dpo: float | None = None                   # delai moyen de paiement

    # ---- Lectures derivees -------------------------------------------------

    @property
    def marge(self) -> float:
        """Part du chiffre d'affaires qui reste apres les depenses."""
        if self.encaissements_par_mois <= 0:
            return 0.0
        return float(self.resultat_par_mois / self.encaissements_par_mois) * 100

    @property
    def part_fixe(self) -> float:
        total = self.charges_fixes + self.charges_variables
        return float(self.charges_fixes / total) * 100 if total > 0 else 0.0

    @property
    def dependance_premier_client(self) -> float:
        return self.concentration[0].part * 100 if self.concentration else 0.0

    @property
    def ecart_de_financement(self) -> float | None:
        """
        DSO moins DPO. Positif : l'entreprise paie ses fournisseurs avant
        d'etre payee — elle finance ses clients sur sa propre tresorerie.
        """
        if self.dso is None or self.dpo is None:
            return None
        return self.dso - self.dpo

    # ---- Mise en mots ------------------------------------------------------

    @staticmethod
    def _n(v) -> str:
        return f"{abs(float(v)):,.0f}".replace(",", " ")

    def messages(self, t=None, nombre=None,
                 symbole: str = "€") -> list[tuple[str, str]]:
        """
        Chaque message dit un fait, puis ce qu'il implique.

        `t` traduit, `nombre` met les montants à la typographie du lecteur.
        Les deux sont injectés : ce module calcule, il ne sait ni dans
        quelle langue ni dans quelle devise on le lira. Ces phrases sont
        restées françaises jusqu'au 13 août 2026 — un client anglophone
        payant le plan Entreprise lisait ses propres indicateurs en
        français.
        """
        t = t or _texte
        somme = nombre or self._n

        out: list[tuple[str, str]] = []

        # --- Runway : le message le plus important quand la marge est negative
        if self.burn_rate < 0:
            if self.runway_mois is not None:
                perte = somme(abs(float(self.burn_rate)))
                if self.runway_mois < 3:
                    out.append(("alerte", t("ent.runway_court", somme=perte,
                                            sym=symbole,
                                            mois=f"{self.runway_mois:.1f}")))
                elif self.runway_mois < 6:
                    out.append(("attention", t("ent.runway_moyen", somme=perte,
                                               sym=symbole,
                                               mois=f"{self.runway_mois:.1f}")))
                else:
                    out.append(("info", t("ent.runway_long", somme=perte,
                                          sym=symbole,
                                          mois=f"{self.runway_mois:.0f}")))
        elif self.resultat_par_mois > 0:
            out.append(("bon", t(
                "ent.benefice", somme=somme(abs(float(self.resultat_par_mois))),
                sym=symbole, p=f"{self.marge:.0f}")))

        # --- Point mort
        if self.point_mort is not None and self.encaissements_par_mois > 0:
            ecart = float(self.encaissements_par_mois - self.point_mort)
            seuil = somme(abs(float(self.point_mort)))
            if ecart < 0:
                out.append(("alerte", t("ent.sous_point_mort",
                                        manque=somme(abs(ecart)),
                                        seuil=seuil, sym=symbole)))
            else:
                marge_secu = ecart / float(self.encaissements_par_mois) * 100
                out.append(("bon" if marge_secu > 20 else "attention",
                            t("ent.au_dessus_point_mort", seuil=seuil,
                              sym=symbole, p=f"{marge_secu:.0f}")))

        # --- Impayes
        if self.encours_client > 0:
            part_retard = (float(self.retard_client / self.encours_client) * 100
                           if self.encours_client else 0)
            if self.retard_client > 0 and part_retard > 25:
                out.append(("alerte", t(
                    "ent.impayes_lourds",
                    somme=somme(abs(float(self.retard_client))), sym=symbole,
                    p=f"{part_retard:.0f}")))
            elif self.retard_client > 0:
                out.append(("attention", t(
                    "ent.impayes",
                    somme=somme(abs(float(self.retard_client))),
                    total=somme(abs(float(self.encours_client))),
                    sym=symbole)))

        # --- Delais
        if self.dso is not None:
            if self.dso > 60:
                out.append(("attention", t(
                    "ent.dso_long", jours=f"{self.dso:.0f}",
                    somme=somme(abs(float(self.encaissements_par_mois) / 3)),
                    sym=symbole)))
            else:
                out.append(("info", t("ent.dso", jours=f"{self.dso:.0f}")))

        ecart_f = self.ecart_de_financement
        if ecart_f is not None and ecart_f > 15:
            out.append(("attention", t("ent.finance_ses_clients",
                                       dpo=f"{self.dpo:.0f}",
                                       dso=f"{self.dso:.0f}",
                                       ecart=f"{ecart_f:.0f}")))
        elif ecart_f is not None and ecart_f < -15:
            out.append(("bon", t("ent.autofinance", dso=f"{self.dso:.0f}",
                                 dpo=f"{self.dpo:.0f}")))

        # --- Dependance client
        if self.concentration:
            premier = self.concentration[0]
            if premier.part > 0.5:
                out.append(("alerte", t("ent.client_majeur",
                                        client=premier.tiers,
                                        p=f"{premier.part * 100:.0f}")))
            elif premier.part > 0.3:
                out.append(("attention", t("ent.client_important",
                                           client=premier.tiers,
                                           p=f"{premier.part * 100:.0f}")))

        # --- Structure de couts
        if self.part_fixe > 70 and self.charges_fixes > 0:
            out.append(("attention", t("ent.msg_charges_fixes",
                                       p=f"{self.part_fixe:.0f}")))

        # --- Croissance
        if self.croissance is not None:
            if self.croissance > 5:
                out.append(("bon", t("ent.croissance",
                                     p=f"{self.croissance:.0f}")))
            elif self.croissance < -5:
                out.append(("attention", t("ent.recul",
                                           p=f"{abs(self.croissance):.0f}")))

        return out


# ===========================================================================
# LE CALCUL
# ===========================================================================

def _mois_couverts(debut: date, fin: date) -> float:
    return max((fin - debut).days / 30.44, 1.0)


def _moyenne_ponderee(valeurs: list[tuple[float, Decimal]]) -> float | None:
    """Moyenne des delais ponderee par les montants : une grosse facture pese plus."""
    poids = sum(float(m) for _, m in valeurs)
    if poids <= 0:
        return None
    return sum(j * float(m) for j, m in valeurs) / poids


def calculer_indicateurs(mouvements=None,
                         factures_clients: list[Facture] | None = None,
                         factures_fournisseurs: list[Facture] | None = None,
                         tresorerie: Decimal | float = 0,
                         au: date | None = None) -> IndicateursEntreprise:
    """
    Calcule les indicateurs a partir de ce qui est disponible.

    Chaque source apporte sa part, et aucune n'est obligatoire :
      · les mouvements bancaires donnent les flux reels, la marge et le runway ;
      · les factures clients donnent le DSO, les impayes et la concentration ;
      · les factures fournisseurs donnent le DPO et l'encours a payer.
    """
    mouvements = list(mouvements or [])
    fc = list(factures_clients or [])
    ff = list(factures_fournisseurs or [])
    aujourdhui = au or date.today()

    # --- Periode couverte
    dates = ([m.jour for m in mouvements]
             + [f.date_emission for f in fc] + [f.date_emission for f in ff])
    if not dates:
        return IndicateursEntreprise(debut=aujourdhui, fin=aujourdhui, nb_mois=1.0)
    debut, fin = min(dates), max(dates)
    nb_mois = _mois_couverts(debut, fin)

    ind = IndicateursEntreprise(debut=debut, fin=fin, nb_mois=nb_mois,
                                tresorerie=_arr(_d(tresorerie)))

    # --- Flux bancaires : la realite de ce qui est entre et sorti
    if mouvements:
        entrees = sum((m.montant for m in mouvements if m.montant > 0), Decimal("0"))
        sorties = sum((m.montant for m in mouvements if m.montant < 0), Decimal("0"))
        ind.encaissements_par_mois = _arr(entrees / Decimal(str(nb_mois)))
        ind.decaissements_par_mois = _arr(sorties / Decimal(str(nb_mois)))
        ind.resultat_par_mois = _arr((entrees + sorties) / Decimal(str(nb_mois)))
        ind.burn_rate = ind.resultat_par_mois

        # Fixe / variable : on reutilise la reconnaissance deja eprouvee
        try:
            from analyse_lisible import _est_une_charge_fixe, nom_lisible
            # On regroupe sur le nom lisible, mais on garde un libelle d'origine :
            # « ACHAT CB » disparait au nettoyage, or c'est justement ce mot qui
            # dit qu'il ne s'agit pas d'une charge fixe.
            groupes: dict[str, list[float]] = defaultdict(list)
            libelles_bruts: dict[str, str] = {}
            for m in mouvements:
                if m.montant < 0:
                    cle = nom_lisible(m.libelle)
                    groupes[cle].append(abs(float(m.montant)))
                    libelles_bruts.setdefault(cle, m.libelle)
            fixes = variables = Decimal("0")
            for cle, montants in groupes.items():
                total = Decimal(str(sum(montants)))
                if _est_une_charge_fixe(libelles_bruts[cle], montants):
                    fixes += total
                else:
                    variables += total
            ind.charges_fixes = _arr(fixes / Decimal(str(nb_mois)))
            ind.charges_variables = _arr(variables / Decimal(str(nb_mois)))
        except Exception:
            ind.charges_fixes = _arr(abs(sorties) / Decimal(str(nb_mois)))

        # Point mort : le CA qui couvre exactement les charges fixes.
        # Taux de marge sur couts variables = (CA - charges variables) / CA.
        ca = ind.encaissements_par_mois
        if ca > 0 and ind.charges_fixes > 0:
            taux = (ca - ind.charges_variables) / ca
            if taux > 0:
                ind.point_mort = _arr(ind.charges_fixes / taux)

        # Runway : combien de mois la tresorerie tient au rythme actuel
        if ind.burn_rate < 0 and ind.tresorerie > 0:
            ind.runway_mois = float(ind.tresorerie / abs(ind.burn_rate))

        # Croissance : moyenne des variations d'un mois complet sur l'autre
        par_mois: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
        for m in mouvements:
            if m.montant > 0:
                par_mois[(m.jour.year, m.jour.month)] += m.montant
        suite = [v for _, v in sorted(par_mois.items())]
        if len(suite) >= 3:                       # 1er et dernier mois souvent partiels
            interieur = suite[1:-1] if len(suite) > 3 else suite
            taux = [float((b - a) / a) * 100 for a, b in zip(interieur, interieur[1:])
                    if a > 0]
            if taux:
                ind.croissance = sum(taux) / len(taux)

    # --- Factures clients
    if fc:
        ind.ca_facture = _arr(sum((f.montant for f in fc), Decimal("0")))
        impayees = [f for f in fc if not f.payee]
        ind.encours_client = _arr(sum((f.montant for f in impayees), Decimal("0")))
        ind.retard_client = _arr(sum((f.montant for f in impayees
                                      if f.jours_de_retard(aujourdhui) > 0), Decimal("0")))

        payees = [f for f in fc if f.payee and f.delai_reglement is not None
                  and f.delai_reglement >= 0]
        if payees:
            ind.dso = _moyenne_ponderee([(f.delai_reglement, f.montant) for f in payees])
        elif ind.ca_facture > 0 and nb_mois > 0:
            # A defaut de paiements connus : encours rapporte au CA quotidien
            ca_jour = float(ind.ca_facture) / (nb_mois * 30.44)
            if ca_jour > 0:
                ind.dso = float(ind.encours_client) / ca_jour

        if ind.ca_facture > 0:
            regle = ind.ca_facture - ind.encours_client
            ind.taux_recouvrement = float(regle / ind.ca_facture) * 100

        par_tiers: dict[str, Decimal] = defaultdict(Decimal)
        for f in fc:
            par_tiers[f.tiers] += f.montant
        total = sum(par_tiers.values()) or Decimal("1")
        ind.concentration = [
            Concentration(t, _arr(m), float(m / total))
            for t, m in sorted(par_tiers.items(), key=lambda x: -x[1])
        ][:10]

    # --- Factures fournisseurs
    if ff:
        ind.achats_factures = _arr(sum((f.montant for f in ff), Decimal("0")))
        ind.encours_fournisseur = _arr(sum((f.montant for f in ff if not f.payee),
                                           Decimal("0")))
        payees = [f for f in ff if f.payee and f.delai_reglement is not None
                  and f.delai_reglement >= 0]
        if payees:
            ind.dpo = _moyenne_ponderee([(f.delai_reglement, f.montant) for f in payees])

    return ind


# ===========================================================================
# PREVISION : des factures vers le calendrier de tresorerie
# ===========================================================================

def factures_vers_operations(factures: list[Facture],
                             au: date | None = None) -> list[dict]:
    """
    Transforme les factures non reglees en operations datees, pretes a etre
    projetees dans le calendrier.

    Une facture deja en retard n'est pas placee dans le passe : on la reporte
    au lendemain, en la marquant incertaine — c'est de l'argent attendu,
    pas de l'argent promis.
    """
    aujourdhui = au or date.today()
    operations = []
    for f in factures:
        if f.payee:
            continue
        quand = f.echeance or (f.date_emission + timedelta(days=30))
        certaine = True
        if quand <= aujourdhui:
            quand = aujourdhui + timedelta(days=1)
            certaine = False                     # en retard : encaissement incertain
        signe = 1 if f.sens == "client" else -1
        operations.append({
            "libelle": f"{'Facture' if f.sens == 'client' else 'À payer'} — {f.tiers}"[:60],
            "montant": signe * float(f.montant),
            "date": quand,
            "devise": f.devise,
            "categorie": "Clients" if f.sens == "client" else "Fournisseurs",
            "certaine": certaine,
        })
    return operations
