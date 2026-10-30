# Test de chauffe supervisé DAMA Lite (Pi 192.168.1.201)

## Contexte du 30 octobre 2026

L'opérateur a confirmé qu'un coupe-circuit thermique indépendant du
Raspberry Pi est installé et qu'il reste sur place pour observer le test.

Le marqueur de qualification **permanente**
\`/etc/dama-lite/heating-qualified\` est toujours absent. On n'autorise pas
la production. Le test temporaire est un programme **distinct**.

## Préconditions

- Protection matérielle indépendante installée (confirmation opérateur).
- Relais câblé pour **HIGH=ON**, **LOW=OFF** (code historique GPIO21).
- En l'absence de courant, résistance réellement OFF.
- Opérateur présent avec un moyen physique de couper l'alimentation.
- Aucune analyse en cours ; staging actif avec \`heating_enabled=false\`.

## Essai limité et journalisé

- L'essai se fait sous une unité systemd désactivée au boot.
- Autorisation temporaire dédiée : \`/etc/dama-lite/heat-test-onsite-approved\`,
  propriété root et lecture publique, sans secret.
- Durée maximale 600 s, et \`RuntimeMaxSec=630\` en second garde-fou.
- Chaque 2 s : température DS18B20, CPU, état du relais GPIO21, défaut.
- Sortie automatique sur : enceinte >=38,5 °C, CPU >=70 °C,
  erreur capteur, saut >=2 °C, aucune augmentation de 0,15 °C
  en 180 s, ou durée expirée.
- Le \`ThermalController\` existant coupe à 37,3 °C et rallume à
  36,7 °C. Il stoppe aussi sur défaut à 41 °C.
- \`ExecStopPost\` force GPIO21 en sortie LOW même après arrêt brutal
  du Python ; la sécurité physique indépendante reste indispensable.
- Journal dans \`heat-test-logs/heat-YYYYMMDDTHHMMSSZ.csv\`.
- Aucun secret SharePoint/Entra traité par le test. Aucun script
  historique \`Programme_complet.py\` exécuté.

## Installation

Après vérification opérateur sur place :

\`\`\`bash
cd /home/damocles/dama-lite-staging
sudo install -o root -g root -m 644 deploy/heat-test-onsite-approved.txt /etc/dama-lite/heat-test-onsite-approved
sudo install -o root -g root -m 644 deploy/dama-lite-heat-test.service /etc/systemd/system/dama-lite-heat-test.service
sudo systemctl daemon-reload
systemctl is-active dama-lite-staging.service
sudo systemctl start dama-lite-heat-test.service
journalctl -fu dama-lite-heat-test.service
\`\`\`

Arrêt volontaire (par utilisateur sur place, au moindre doute) :

\`\`\`bash
sudo systemctl stop dama-lite-heat-test.service
\`\`\`

La coupure physique doit rester disponible. Ne jamais modifier
\`dama-lite-staging.service\` pour y activer la chauffe ni créer
artificiellement le marqueur permanent de qualification.

**Ce test n'établit pas à lui seul la tenue de régulation 30 minutes.**
Même si T atteint 37 °C en 600 s, il faut une seconde campagne qualifiée
pour stabilité et contrôle d'un thermomètre indépendant.


## Utilisation depuis l'écran tactile

La zone « CHAUFFE OFF · TOUCHER » est désormais une commande :
elle ouvre un écran d'essai limité et distinct du profil principal.
Un essai permanent ne peut pas être activé depuis cet écran.

L'appareil présente :
- la température enceinte et CPU, les confirmations de présence et de
  protection thermique indépendante ;
- le bouton « Démarrer l'essai (10 min) » lorsqu'il est **armé par root** ;
- le bouton « Arrêter la chauffe d'essai » à tout moment ;
- un état de service distinct du badge de chauffe permanente.

Après contrôle physique du relais (NO / LOW=OFF) et de la protection,
l'opérateur habilité peut armer **temporairement** le banc local :

    sudo install -o root -g root -m 644 \
      /home/damocles/dama-lite-staging/deploy/heat-test-onsite-approved.txt \
      /etc/dama-lite/heat-test-onsite-approved

Cet armement devient automatiquement caduc après **15 minutes**.
Il n'est pas réutilisable sans nouvelle vérification sur place.
Un essai déjà démarré se poursuit au plus 10 minutes sous ses propres
surveillances ; expirer le marqueur ne prolonge jamais un essai.

Les commandes tactiles demandent uniquement START/STOP à la passerelle
root préinstallée, qui ne possède aucun accès à des commandes arbitraires.
La chauffe reste désactivée dans le service staging et toute analyse
reste bloquée jusqu'à qualification distincte de la production.
