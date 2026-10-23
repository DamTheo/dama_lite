# Préinstallation de DAMA Lite : audit matériel en lecture seule

La commande de diagnostic **ne change aucun état GPIO** et ne démarre ni
caméra, ni chauffage, ni LED, ni service. Elle lit seulement des fichiers système
et exécute des commandes de consultation (\`systemctl is-active\`,
\`timedatectl show\`, \`pinctrl get\` ou \`raspi-gpio get\`).

Depuis la copie Git sur Incub-resa (ultérieurement) :

\`\`\`bash
cd /opt/dama-lite
PYTHONPATH=backend python3 -m dama_lite.preflight
# Après création de la configuration, sans afficher les secrets :
PYTHONPATH=backend python3 -m dama_lite.preflight --config /etc/dama-lite/config.json
\`\`\`

Le résultat JSON permet de compléter la fiche de qualification :
modèle de Pi, versions OS, température DS18B20, CPU, chemin des webcams,
présence de l'écran, services, anciennes instances de Programme_complet.py,
signaux GPIO lus sans les modifier, synchronisation horloge, capacité disque et
état des paramètres de sécurité.

Il ne confirme PAS la polarité électrique réelle du relais ou la présence
d'une sécurité thermique indépendante : cela exige un contrôle physique.

Si \`legacy_gpio_processes\` contient Programme_complet.py, Programme.py ou
Test_LED.py, désactiver proprement l'ancien superviseur **après validation
de la procédure de migration**, avant d'activer chauffage/LED de DAMA Lite.

Le programme \`test_temperature.py\` ne commande pas d'actionneur et n'est
donc pas bloquant pour l'accès exclusif aux GPIO.

## Synchronisation SharePoint vérifiée

Sur PC01, le chemin d'expérimentations donné par l'utilisateur appartient à
la bibliothèque **R&D Biologie** du site **DAMOCLES DX – Intranet**.
Le backend doit utiliser le **drive ID correspondant à cette bibliothèque**,
pas celui de Documents ou de OneDrive. Le drive ID et les identifiants Graph
doivent rester dans la configuration locale non publiée.

La destination est directement \`DAMA-Lite/<nom_du_test>/\` après les dossiers
\`03_Projets/04_Résazurine/03_Expérimentations & Résultats\` de cette bibliothèque.
