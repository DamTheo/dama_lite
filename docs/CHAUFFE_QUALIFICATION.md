# Remise en service du chauffage — protection indispensable

Le chauffage ne fonctionne pas dans \`dama-lite-staging.service\` parce que
\`heating_enabled=false\`, en raison du blocage explicite
\`safe_staging\`. Le GPIO21 reste en entrée, ce qui protège les
résistances contre une commande logicielle non validée.

## Audit du code historique

\`/home/damocles/Programme_complet.py\` atteste un relais
**GPIO21 actif au niveau haut**, initialisé à \`False\` (chauffe coupée),
puis basculé à \`True\` si la température DS18B20 est sous 37 °C.
C'est une indication logicielle, **pas une preuve du câblage actuel**,
ni de la présence d'une sécurité indépendante.

Le contrôleur DAMA Lite ajoute :
- Consigne 37 °C, hystérésis 0,3 °C.
- Démarrage d'analyse seulement à partir de 35 °C.
- Sonde DS18B20 GPIO22 avec trois essais CRC ; échec = relais OFF
  et défaut verrouillé.
- Limite logiciel enceinte 41 °C.
- Alerte CPU dès 65 °C, limite de coupure 80 °C.
- Arrêt du relais avant fermeture des sockets, du stockage ou de Graph.

## Protection physique avant toute activation

À confirmer **sur l'appareil**, résistances déconnectées lors de
l'essai de logique :

1. Le contact du relais est **normalement ouvert**, et la résistance
   est réellement éteinte si le Pi est coupé, débranché ou figé.
2. Un **thermostat de sécurité ou fusible thermique indépendant**
   coupe l'alimentation des résistances même si le relais reste collé.
3. Le relais est bien actif-haut (GPIO21) et supporte le courant des
   résistances et les tensions concernées.
4. La DS18B20 est fixée à l'emplacement représentatif ; les huit
   zones ont des écarts de température acceptables.
5. Mesurer la coupure réelle, la montée à 37 °C, le dépassement
   après inertie et les défauts de débranchement de sonde.
6. Valider le bouton d'extinction physique et la gestion
   des reprises après coupure secteur.

Le gabarit \`dama-lite.service\` contient une garde \`ExecStartPre\`.
Elle refuse le chauffage à moins qu'un opérateur ait enregistré sur
le Pi **un marqueur root protégé 0600** nommé
\`/etc/dama-lite/heating-qualified\`, de valeur exacte
\`CUTOFF_INDEPENDENT_VERIFIED_GPIO21_ACTIVE_HIGH\`.

La garde relit aussi trois mesures de sonde et la température CPU
avant de démarrer le service. Elle ne commande jamais GPIO21.

**La présence du marqueur est une attestation manuelle**, pas une
preuve matérielle. Ne pas le créer sans avoir réellement qualifié
la protection indépendante et le relais. Le mode staging actuel
n'est volontairement pas modifié pour autoriser la chauffe.

Après qualification, utiliser une installation de production
documentée et séparer le compte HTTP/Graph des privilèges nécessaires
aux LED. Les évolutions de chauffage ne doivent jamais être essayées
dans le service staging de contrôle des caméras.
