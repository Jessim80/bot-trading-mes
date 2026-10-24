# 🤖 Bot de trading MES — Opening Range Breakout

Ton assistant de trading automatique. Chaque jour de bourse, il t'envoie sur Telegram :

| Heure (Paris) | Message | Contenu |
|---|---|---|
| ~45 min avant l'ouverture NY | ☀️ **Brief du matin** | Verdict 🟢/🟠/🔴, niveaux clés, annonces du jour, contexte IA, tableau du nombre de contrats |
| juste après le range (~15 min après l'ouverture) | 🎯 **Plan de trade** | Ordres exacts : entrée, stop-loss, objectif, nombre de contrats |
| chaque samedi | 📊 **Backtest** | La stratégie est re-testée : validée ✅ ou non ❌ |

## 💸 Coût : 0 €

| Brique | Service | Prix |
|---|---|---|
| Exécution automatique | GitHub Actions (2 000 min/mois offertes, le bot en utilise ~700) | 0 € |
| Messages | Telegram | 0 € |
| Données de marché + actualités | Yahoo Finance, CNBC (RSS), ForexFactory | 0 € |
| Résumé IA | Google Gemini, offre gratuite (1 seul appel par jour) | 0 € |
| Compte de trading démo | Simulateur NinjaTrader | 0 € |

Aucune carte bancaire n'est demandée nulle part. Si l'offre gratuite de Gemini change ou si le quota est atteint, le bot envoie quand même le brief avec les titres d'actualité bruts, sans résumé.

> ⚠️ **Démo uniquement** tant que le backtest n'affiche pas ✅ **ET** que tu n'as pas fait 30 trades rentables en démo.
> Ce bot ne garantit aucun gain. Ce n'est pas un conseil financier.

L'ouverture de New York est à **15h30** (heure de Paris), sauf environ deux semaines par an où la France et les États-Unis ne changent pas d'heure le même jour. Cette année, du 26 au 30 octobre 2026, c'est **14h30**. Le bot gère ça tout seul.

---

## ✅ Installation (une seule fois, ~15 min)

### 1. Créer ton bot Telegram
1. Dans Telegram, ouvre **@BotFather** → envoie `/newbot` → choisis un nom.
2. Il te donne un **token** (ex. `7123456:AAF...`). Garde-le.
3. Ouvre ton nouveau bot et envoie-lui « salut ».
4. Va sur `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` → repère `"chat":{"id":123456789` : c'est ton **chat id**.

### 2. Créer ta clé IA gratuite (optionnel mais recommandé)
Va sur **aistudio.google.com** avec ton compte Google → **Get API key** → **Create API key**. Aucune carte bancaire.
⚠️ N'active **jamais** la facturation (« billing ») sur ce projet Google : comme ça, c'est impossible d'être débité.

### 3. Ajouter les secrets sur GitHub
Dans ce dépôt : **Settings → Secrets and variables → Actions → New repository secret** :

| Nom | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | le token de BotFather |
| `TELEGRAM_CHAT_ID` | ton chat id |
| `GEMINI_API_KEY` | ta clé Google AI Studio |

### 4. Lancer le premier backtest
Onglet **Actions** → **Bot de trading** → **Run workflow** → choisis **backtest** → **Run workflow**. Tu reçois les résultats sur Telegram en ~3 min.
Teste aussi **brief** et **plan** de la même façon (en test, le plan utilise la dernière séance).

C'est tout : ensuite tout tourne seul, du lundi au vendredi.

---

## 🧠 La stratégie (simple et mécanique)

1. De 15h30 à 15h45 (Paris), le bot note le **plus haut** et le **plus bas** : c'est le *range d'ouverture*.
2. Un ordre d'**achat** 1 tick au-dessus du haut, un ordre de **vente** 1 tick sous le bas, en **OCO** (le premier exécuté annule l'autre).
3. **Stop-loss** de l'autre côté du range, **objectif** à 1,5 fois le risque.
4. Pas touché à 17h30 (Paris) → tu sors. **Un seul trade par jour.**
5. **Pas de trade** les jours de Fed, quand une grosse annonce tombe pendant la fenêtre, ou quand le VIX dépasse 30.

Taille : le bot calcule le nombre de contrats MES pour ne jamais risquer plus de **200 $** par trade (modifiable dans `config.yaml`).

## 🛡 Règles d'or
- Tu ne déplaces **jamais** ton stop-loss.
- 🔴 = tu ne trades pas, même si « ça a l'air évident ».
- 3 pertes d'affilée → tu arrêtes pour la journée et tu relis tes trades.
- Tu ne changes pas les réglages juste après une perte.

## ⚙️ Limites à connaître
- Les données gratuites de Yahoo ont **~10 min de retard** sur les futures : le brief te donne le tableau des tailles pour placer tes ordres **toi-même** dès 15h45, et le plan du bot sert de vérification.
- Les horaires GitHub peuvent avoir quelques minutes de retard.
- Le backtest gratuit couvre les **60 derniers jours** environ. Pour un test sur plusieurs années : `python -m src.backtest --csv historique.csv`.

## 🔧 Tester en local (optionnel)
```bash
pip install -r requirements.txt
python -m pytest -q          # 16 tests automatiques
DRY_RUN=1 FORCE=1 python -m src.brief   # affiche le brief sans l'envoyer
```
