"""
Verification que rien ne se perd.

Ce test protege une lecon apprise a la dure : l'application affichait
« Enregistre a 18:25 » alors qu'un compte ajoute ensuite n'etait jamais
parti en base. L'utilisateur croyait ses donnees sauvegardees.

La regle : TOUTE action qui modifie les donnees doit etre suivie d'un
enregistrement. Ce test echoue si quelqu'un ajoute une action sans le faire.

Lancer :  py test_enregistrement.py
"""

import re
from pathlib import Path

ok, ko = 0, []


def verifier(nom, obtenu, attendu=True):
    global ok
    if obtenu is attendu:
        ok += 1
        print(f"  ok    {nom}")
    else:
        ko.append(nom)
        print(f"  ECHEC {nom}")


# Chaque motif est une action qui modifie les donnees de l'utilisateur.
ACTIONS = [
    (r"operations\.append",      "ajout d'une opération"),
    (r"operations\.pop",         "suppression d'une opération"),
    (r"operations\.extend",      "ajout de factures au calendrier"),
    (r"operations = \[\]",       "effacement de toutes les opérations"),
    (r"\.ajouter\(Compte",       "ajout d'un compte"),
    (r"\.retirer\(",             "retrait d'un compte"),
    (r"definir_reference",       "changement de devise de référence"),
    (r"\.ajouter\(Taux",         "ajout d'un taux de change"),
]

FICHIERS = ["app_tresorerie.py", "vue_comptes.py", "vue_entreprise.py"]

# La regle n'est pas « dans les N lignes » — ce serait arbitraire, et un
# bloc un peu long la ferait echouer a tort. La vraie regle est :
# entre la modification et le rechargement de l'ecran, il doit y avoir
# un enregistrement. C'est cela qu'on verifie.
LIMITE_RECHERCHE = 40


def _enregistre_avant_rechargement(lignes: list[str], depart: int) -> bool:
    """
    Cherche `commun.enregistrer()` entre la modification et le prochain
    `st.rerun()`, qui marque la fin du traitement de l'action.

    Un enregistrement place apres le rechargement ne servirait a rien :
    le script est relance depuis le debut et la ligne n'est jamais atteinte.
    """
    for ligne in lignes[depart:depart + LIMITE_RECHERCHE]:
        if "commun.enregistrer()" in ligne:
            return True
        if "st.rerun()" in ligne:
            return False        # rechargement atteint sans enregistrement
    return False


print("\n1. Toute modification declenche un enregistrement")

trouvees = 0
for nom_fichier in FICHIERS:
    chemin = Path(nom_fichier)
    if not chemin.exists():
        continue
    lignes = chemin.read_text(encoding="utf-8").split("\n")
    for i, ligne in enumerate(lignes):
        if ligne.lstrip().startswith("#"):
            continue
        for motif, description in ACTIONS:
            if re.search(motif, ligne):
                trouvees += 1
                verifier(f"{nom_fichier}:{i + 1} — {description}",
                         _enregistre_avant_rechargement(lignes, i))

# Si ce compte tombe a zero, c'est que les motifs ne correspondent plus
# au code : le test passerait alors sans rien verifier.
print(f"\n2. Le test verifie bien quelque chose")
verifier(f"{trouvees} actions inspectees (attendu : au moins 8)",
         trouvees >= 8)


print("\n3. L'ecran ne ment pas sur l'etat")

vue = Path("vue_compte.py").read_text(encoding="utf-8")
verifier("un enregistrement en echec est signale",
         "erreur_sauvegarde" in vue)
verifier("des modifications en attente sont signalees",
         "modifications_en_attente" in vue)
verifier("le mot « Enregistré » n'apparait qu'en cas de succes",
         vue.index("modifications_en_attente") < vue.index("Enregistré à"))

commun = Path("commun.py").read_text(encoding="utf-8")
verifier("l'etat est remis a zero apres un enregistrement reussi",
         "modifications_en_attente = False" in commun)
verifier("l'etat est leve quand l'enregistrement echoue",
         "modifications_en_attente = True" in commun)


print("\n4. L'enregistrement va au bon endroit")

verifier("connecte : la base fait autorite",
         "compte.connecte()" in commun and "_enregistrer_en_base" in commun)
verifier("en ligne sans compte : aucune ecriture",
         "if not sv.mode_local():" in commun)
verifier("local : fichier sur le poste",
         "sv.enregistrer(donnees)" in commun)


print("\n" + "=" * 62)
if ko:
    print(f"{ok} verifications reussies, {len(ko)} ECHECS :")
    for n in ko:
        print(f"   - {n}")
    raise SystemExit(1)
print(f"{ok} verifications reussies, aucun echec.")
