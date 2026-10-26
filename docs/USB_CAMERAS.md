undefined

## État machine ≠ état de chaque caméra

Le premier essai avec huit caméras a révélé que le verrouillage thermique
DS18B20 colorait les huit tuiles en rouge, malgré huit ports UVC accessibles
et de vraies images en MJPEG. Le backend distingue désormais :
- \`camera.health\` : disponibilité propre à la caméra, aux sessions et à
  ses transmissions ;
- \`camera.led\` : commande matérielle des huit LED de position qui peut
  volontairement devenir rouge en cas de défaut thermique **global**.

Un incident de sonde reste signalé dans le bandeau thermique et interdit
la chauffe/l'analyse ; il **n'est plus présenté comme huit webcams en panne**.
Le verrouillage de sécurité de la sonde n'a pas été supprimé.
