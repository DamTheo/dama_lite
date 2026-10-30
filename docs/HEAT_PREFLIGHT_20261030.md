# Qualification de la chauffe DAMA Lite — 30/10/2026

## Conditions observées

- Incubateur Raspberry Pi 4, GPIO21 dédié au relais (état initial entrée).
- DS18B20 sur GPIO22 (W1, CRC YES), ID 28-0000006ca681.
- Consigne enceinte 37 °C, démarrage expérience autorisé à 35 °C.
- Hystérésis logicielle : chauffe ON <= 36,7 °C ; OFF >= 37,3 °C.
- Défaillance de la sonde, enceinte >=41 °C ou CPU >=80 °C :
  relais OFF et défaut verrouillé ; alerte CPU dès 65 °C.
- La télémétrie CPU manquante interdit désormais la chauffe.
- Aucun marqueur root /etc/dama-lite/heating-qualified installé.
- Service staging volontairement chauffant désactivé.
- Le profil de production n'est pas installé dans /opt/dama-lite.

## Test réalisé sans énergie

Commande sur Incub-resa :
    cd /home/damocles/dama-lite-staging
    PYTHONPATH=backend python3 -m dama_lite.thermal_preflight \
      --config /home/damocles/dama-lite-staging/config.staging.json

Lecture réelle DS18B20 et CPU, relais de sortie simulé en mémoire.
Ne crée pas d'autorisation matérielle, ne modifie aucune sortie GPIO.

## Qualification physique obligatoire avant premier ON

Un opérateur sur place doit contrôler et consigner :
1. alimentation de la résistance et puissance électrique ;
2. type du relais, polarité active HIGH/LOW et borne NC/NO câblée ;
3. état arrêt/deconnexion = chauffage réellement hors tension ;
4. coupe-circuit thermique indépendant du Raspberry Pi, emplacement,
   seuil de déclenchement et vérification du fonctionnement ;
5. absence de matière inflammable dans la zone chaude ;
6. présence d'un opérateur avec coupure électrique accessible pendant
   la première montée, thermomètre indépendant et arrêt d'urgence.

Ne PAS créer artificiellement le marqueur de qualification si ces
contrôles n'ont pas été réalisés. Un thermomètre logiciel ou la
température CPU ne remplace pas un coupe-circuit matériel.

Une fois le matériel qualifié, prévoir un essai initial limité
dans le temps, journalisé en continu (DS18B20 + CPU), avec
arrêt immédiat sur défaut, puis test de régulation autour de 37 °C.
Ne pas activer ce chauffage au premier essai à distance sans supervision.
