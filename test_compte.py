"""
Verification du module compte — parties testables sans reseau.

Le cycle reseau complet (inscription, connexion, ecriture) se verifie sur
l'application deployee : voir le protocole dans le memo.

L'isolation entre utilisateurs, elle, est garantie par PostgreSQL et non
par ce module : elle a ete eprouvee directement en base.

Lancer :  py test_compte.py
"""

from datetime import date
from decimal import Decimal

import compte

ok, ko = 0, []


def verifier(nom, obtenu, attendu):
    global ok
    reussi = (obtenu is attendu) if isinstance(attendu, bool) else (obtenu == attendu)
    if reussi:
        ok += 1
        print(f"  ok    {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : obtenu {obtenu!r}, attendu {attendu!r}")


def leve(nom, fonction, fragment=""):
    global ok
    try:
        fonction()
    except compte.ErreurCompte as err:
        if fragment and fragment.lower() not in str(err).lower():
            ko.append(nom)
            print(f"  ECHEC {nom} : message inattendu « {err} »")
            return
        ok += 1
        print(f"  ok    {nom}")
    except Exception as err:
        ko.append(nom)
        print(f"  ECHEC {nom} : mauvaise exception {type(err).__name__}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom} : aucune erreur levee")


# ---------------------------------------------------------------------------
print("\n1. Configuration absente — l'application reste utilisable")
# ---------------------------------------------------------------------------

vide = compte.Configuration()
verifier("configuration vide inactive", vide.active, False)
verifier("url sans cle : inactive",
         compte.Configuration(url="https://x.supabase.co").active, False)
verifier("cle sans url : inactive",
         compte.Configuration(cle_publique="abc").active, False)
verifier("les deux : active",
         compte.Configuration(url="https://x.supabase.co",
                              cle_publique="abc").active, True)

# Sans configuration, l'application ne doit pas planter mais l'annoncer.
leve("client refuse sans configuration", compte.client, "pas configur")


# ---------------------------------------------------------------------------
print("\n2. Controle des saisies — avant tout appel reseau")
# ---------------------------------------------------------------------------

# Ces refus ont lieu AVANT le reseau : ils sont donc testables ici, et
# evitent un aller-retour inutile pour une saisie manifestement fausse.
leve("inscription sans adresse",
     lambda: compte.inscrire("", "MotDePasse123"), "adresse")
leve("inscription adresse sans arobase",
     lambda: compte.inscrire("pas-une-adresse", "MotDePasse123"), "adresse")
leve("mot de passe trop court",
     lambda: compte.inscrire("a@b.fr", "court"), "8 caractères")
leve("mot de passe vide",
     lambda: compte.inscrire("a@b.fr", ""), "8 caractères")

leve("connexion sans adresse",
     lambda: compte.connecter("", "MotDePasse123"), "adresse")
leve("connexion sans mot de passe",
     lambda: compte.connecter("a@b.fr", ""), "mot de passe")

leve("reinitialisation sans adresse",
     lambda: compte.reinitialiser_mot_de_passe(""), "adresse")
leve("reinitialisation adresse invalide",
     lambda: compte.reinitialiser_mot_de_passe("xxx"), "adresse")

# Le seuil est a 8 caracteres : une donnee financiere merite mieux que 6.
leve("7 caracteres refuses", lambda: compte.inscrire("a@b.fr", "1234567"),
     "8 caractères")


# ---------------------------------------------------------------------------
print("\n3. Messages traduits — aucun jargon anglais a l'ecran")
# ---------------------------------------------------------------------------

cas = [
    ("Invalid login credentials", "Adresse ou mot de passe incorrect."),
    ("Email not confirmed", "confirmée"),
    ("User already registered", "existe déjà"),
    ("Password should be at least 6 characters", "6 caractères"),
    ("Unable to validate email address", "pas valide"),
    ("For security purposes, you can only request this after 60 seconds",
     "Patientez"),
]
for anglais, attendu_fr in cas:
    rendu = compte._messages_lisibles(Exception(anglais))
    verifier(f"« {anglais[:34]}… »", attendu_fr in rendu, True)

# Une erreur inconnue ne doit pas exposer de trace technique.
inconnue = compte._messages_lisibles(Exception("KeyError at 0x7f3a: null pointer"))
verifier("erreur inconnue : message neutre",
         "0x7f3a" not in inconnue and "KeyError" not in inconnue, True)
verifier("erreur inconnue : reste utile",
         "réessayez" in inconnue.lower(), True)


# ---------------------------------------------------------------------------
print("\n4. Reinitialisation : ne pas reveler qui est inscrit")
# ---------------------------------------------------------------------------

# La reponse doit etre identique que l'adresse existe ou non, sinon elle
# devient un moyen de savoir qui possede un compte.
compte.configuration = lambda: compte.Configuration()   # force l'absence
try:
    compte.reinitialiser_mot_de_passe("inconnu@exemple.fr")
    verifier("reinitialisation sans configuration signalee", False, True)
except compte.ErreurCompte as err:
    verifier("reinitialisation sans configuration signalee",
             "configur" in str(err).lower(), True)


# ---------------------------------------------------------------------------
print("\n5. Conversion des valeurs vers la base")
# ---------------------------------------------------------------------------

verifier("date en texte ISO", compte._en_texte(date(2026, 9, 5)), "2026-09-05")
verifier("absence de date reste vide", compte._en_texte(None), None)
verifier("texte deja pret", compte._en_texte("2026-09-05"), "2026-09-05")

from moteur_tresorerie import Recurrence
verifier("recurrence en texte",
         compte._valeur(Recurrence.MENSUELLE), "mensuelle")
verifier("texte deja pret", compte._valeur("ponctuelle"), "ponctuelle")

# Le point qui protege l'exactitude : un montant part en TEXTE.
verifier("un Decimal devient du texte exact",
         str(Decimal("42000.50")), "42000.50")
verifier("... sans notation scientifique",
         "E" not in str(Decimal("0.001524")), True)


# ---------------------------------------------------------------------------
print("\n6. Session")
# ---------------------------------------------------------------------------

s = compte.Session(identifiant="abc", email="a@b.fr")
verifier("session porte l'identifiant", s.identifiant, "abc")
verifier("session porte l'adresse", s.email, "a@b.fr")
verifier("espace vide par defaut", s.espace_id, "")


print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
