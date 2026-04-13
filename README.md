# Port-Louis Surf Dashboard

Données live via [Stormglass.io](https://stormglass.io) · Mise à jour toutes les 3h via GitHub Actions.

## Setup

1. Fork ce repo sur GitHub
2. Ajoute ton secret Stormglass :
   - **Settings → Secrets and variables → Actions → New repository secret**
   - Nom : `SG_KEY`
   - Valeur : ta clé Stormglass
3. Active GitHub Pages :
   - **Settings → Pages → Source : Deploy from branch → main → /docs**
4. Lance le workflow manuellement :
   - **Actions → Surf Dashboard → Run workflow**
5. Ton dashboard est dispo sur `https://[ton-username].github.io/[nom-repo]/`

## Local

```bash
pip install requests
SG_KEY=ta_cle python3 surf_portlouis.py
open docs/index.html
```
